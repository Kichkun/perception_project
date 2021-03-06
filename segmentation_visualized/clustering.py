import copy
import time
from os import listdir
from os.path import isfile, join

import imageio
import matplotlib
from sklearn import cluster, preprocessing
from sklearn.cluster import AgglomerativeClustering, DBSCAN, SpectralClustering
from progress.bar import FillingCirclesBar
#import whitebox
from sklearn.preprocessing import normalize

matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import mpl_toolkits.mplot3d.axes3d as p3
import numpy as np
from numpy import dot
from numpy.linalg import inv, norm, svd, solve
from mpl_toolkits.mplot3d import Axes3D

import pykitti
import open3d
#whitebox.whitebox_tools.WhiteboxTools.

def get_point_cloud(dataset, pcs_step, take_each_n_point, ax):
    pc_s = np.zeros((0, 3))
    shape_s = np.zeros(int(max_range/pcs_step))
    # Collect point clouds
    for i in np.arange(0, max_range, pcs_step):
        curr = dataset.poses[i][:, 3]

        # Select n points from i-th point cloud
        pc = dataset.get_velo(i)
        pc = pc[range(0, pc.shape[0], take_each_n_point)]

        # Transform from velodyne (X) to left camera coordinates (x): x = Tr * X
        Tr = dataset.calib.T_cam0_velo[:3, :]
        pc = np.array([dot(Tr, i) for i in pc])
        pc += curr[:3]

        pc_s = np.vstack((pc_s, pc))
        shape_s[int(i/pcs_step)] = int(pc.shape[0])
    return pc_s, shape_s
def get_one_point_cloud_turned(dataset, n_cloud, take_each_n_point, centroid, rotated_centroid):
    curr = dataset.poses[n_cloud][:, 3]
    pc = dataset.get_velo(n_cloud)
    pc = pc[range(0, pc.shape[0], take_each_n_point)]
    Tr = dataset.calib.T_cam0_velo[:3, :]
    pc = np.array([dot(Tr, i) for i in pc])
    pc += curr[:3]
    pc -= centroid

    pc_turned = pc * M+rotated_centroid
    return pc_turned

def get_trajectory(dataset):
    trajectory = np.zeros((0, 3))

    # Collect odometry
    for i in np.arange(0, max_range):
        curr = dataset.poses[i][:, 3]
        trajectory = np.vstack((trajectory, curr[:3]))

    return trajectory


def compute_z(X, Y, plane_coeffs):
    return plane_coeffs[0] * X + plane_coeffs[1] * Y + plane_coeffs[2]


def calculate_rotation_matrix(a, b):
    v = np.cross(a, b)
    c = np.dot(a, b)
    I = np.identity(3)

    vx = np.matrix([0, -v[2], v[1], v[2], 0, -v[0], -v[1], v[0], 0]).reshape((3, 3))

    return I + vx + np.matmul(vx, vx) / (1 + c)

def find_best_fitting_plane(trajectory, ax):
    # First use SVD to find normal of plane and calculate transformation to z-oriented view
    # Center all points
    centroid = [trajectory[:, 0].sum() / trajectory.shape[0],
                trajectory[:, 1].sum() / trajectory.shape[0],
                trajectory[:, 2].sum() / trajectory.shape[0]]

    centered_trajectory = trajectory - centroid

    # Apply SVD
    u, s, vh = svd(centered_trajectory.T, full_matrices=True)

    # Normal
    normal = u[:, 2]

    # Applied in a way: dot(point, M)
    M = calculate_rotation_matrix(np.array([0, 0, 1]), normal)

    normal = np.array(*dot(normal, M).tolist())

    rotated_trajectory = centered_trajectory[:, :] * M
    rotated_centroid = np.array(*dot(centroid,M).tolist())

    trajectory = rotated_trajectory
    trajectory += rotated_centroid

    # Use least squares to find best fitting plane along z coordinate

    A = np.zeros((trajectory.shape[0], 3))
    A[0:, 0] = trajectory[0:, 0].reshape((trajectory.shape[0],))
    A[0:, 1] = trajectory[0:, 1].reshape((trajectory.shape[0],))
    A[0:, 2] = 1

    b = np.zeros((trajectory.shape[0], 1))
    b[0:, 0] = trajectory[0:, 2].reshape((trajectory.shape[0],))

    # ax + by + c = z
    # Here: a, b and c
    plane_coeffs = solve(dot(A.T, A), dot(A.T, b))

    lx = -100
    ly = -300
    ux = 150
    uy = 100
    num = 10

    base = np.array([0.0, 0.0, 0.0])
    base += rotated_centroid
    normal += rotated_centroid

    ax.plot([base[0], normal[0]], [base[1], normal[1]], [base[2], normal[2]])

    X, Y = np.meshgrid(np.arange(lx, ux, (ux - lx) / num), np.arange(ly, uy, (uy - ly) / num))
    Z = compute_z(X, Y, plane_coeffs)

    ax.plot_wireframe(X, Y, Z, color='dimgray')

    return trajectory, centroid, rotated_centroid, M


def calc_metrics(pcds, labels):
    cov = []
    k = len(np.unique(labels))
    #print(k)
    means = np.zeros((k, 3))
    r = np.zeros(k)
    var = np.zeros((k, 3))
    mins = np.zeros((k, 3))
    maxes = np.zeros((k, 3))
    for l in np.unique(labels):
        means[l, 0] = pcds[labels == l, 0].mean()
        means[l, 1] = pcds[labels == l, 1].mean()
        means[l, 2] = pcds[labels == l, 2].mean()
        var[l, 0] = pcds[labels == l, 0].var()
        var[l, 1] = pcds[labels == l, 1].var()
        var[l, 2] = pcds[labels == l, 2].var()
        mins[l, 0] = pcds[labels == l, 0].min()
        mins[l, 1] = pcds[labels == l, 1].min()
        mins[l, 2] = pcds[labels == l, 2].min()
        maxes[l, 0] = pcds[labels == l, 0].max()
        maxes[l, 1] = pcds[labels == l, 1].max()
        maxes[l, 2] = pcds[labels == l, 2].max()
        r[l] = np.sqrt(
            (maxes[l, 0] - mins[l, 0]) ** 2 + (maxes[l, 1] - mins[l, 1]) ** 2 + (maxes[l, 2] - mins[l, 2]) ** 2) / 2
        a = means[l, 0:2]
        b = pcds[labels == l].shape[0]
        c = pcds[labels == l, 0:2]
        z = c - np.matlib.repmat(a, b, 1)
        cov_new = (1 / pcds[labels == l, 0:2].shape[1]) * np.dot(z, z.transpose())
        cov.append(cov_new)
        #print(r[l])
    cov = np.array(cov)
    return means, cov, var, mins, maxes, r

def clustering(pc_s, pcs_step, clusters_per_pair ):

    k = 0
    #print(pc_s.shape)
    means_s = np.zeros((clusters_per_pair*int(max_range/(pcs_step)),3))
    r_s = np.zeros(clusters_per_pair*int(max_range/2))
    ind_1 = 0
    ind_2 = 0
    i = pcs_step*2
    for j in range(0, pcs_step):
        ind_2 += int(shape_s[j])
    for i in range(0, max_range, pcs_step):
        ward = AgglomerativeClustering(clusters_per_pair, linkage='ward').fit(pc_s[ind_1:ind_2])
        label = ward.labels_
        means, cov, vars, mins, maxes, r = calc_metrics(pc_s[ind_1:ind_2], label)
        #print(np.cov(pc_s[label == 1]).shape)
        means_s[k:k+clusters_per_pair] = means
        #print("i - pcs_step")
        #print(i-pcs_step)
        r_s[k:k+clusters_per_pair] = r
        k += clusters_per_pair
        ind_1 = ind_2
        a = i
        b = i+pcs_step
        for j in range(a, b):
            ind_2 += int(shape_s[j])
        #print(ind_1)
        #print(ind_2)

        #print("k")
        #print(k)
    #print(means_s)
    #print(means_s.shape)
    return means_s, r_s

def correspondences(dataset, means_s, pcs_step, clusters_per_pair, take_each_n_point, trashold):
    num_of_clusters = clusters_per_pair*int(max_range/(pcs_step))
    print(num_of_clusters)
    corr = []
    progress_bar = FillingCirclesBar('Correspondences calculation', max=num_of_clusters)
    for i in range(0,int(num_of_clusters/clusters_per_pair)):
        for j in range(i*pcs_step, (i+1)*pcs_step):
            pc = get_one_point_cloud_turned(dataset, j, take_each_n_point, centroid, rotated_centroid)
            outp = 0
            for k in range(0, pc.shape[0]):
                pc_c = pc[k]
                mean = means_s[i].reshape(1,-1)
                sc = 0
                for poi in range(0,3):
                    if ((mean[0, poi]>=pc_c[0, poi]-trashold)and(mean[0, poi]<=pc_c[0, poi]+trashold)):
                        sc += 1
                if (sc==3):
                    outp+=1
                else:
                    outp+=0
                #outp.append(sc)
            #print(j)
            progress_bar.next()
            if (outp>1):
                corr.append(1)
            else:
                corr.append(0)
    corr = np.array(corr)
    progress_bar.finish()
    return corr

def correspondences_new(dataset, means_s, pcs_step, clusters_per_pair, take_each_n_point, trashold):
    num_of_clusters = clusters_per_pair*int(max_range/(pcs_step))
    #print(num_of_clusters)
    corr_s = np.zeros((num_of_clusters, max_range))
    progress_bar = FillingCirclesBar('Correspondences calculation', max=num_of_clusters*max_range)
    for i in range(0, num_of_clusters):
        for j in range(0, max_range):
            pc = get_one_point_cloud_turned(dataset, j, take_each_n_point, centroid, rotated_centroid)
            outp = 0
            for k in range(0, pc.shape[0]):
                pc_c = pc[k]
                mean = means_s[i].reshape(1,-1)
                sc = 0
                for poi in range(0,3):
                    if ((mean[0, poi]>=pc_c[0, poi]-trashold)and(mean[0, poi]<=pc_c[0, poi]+trashold)):
                        sc += 1
                if (sc==3):
                    outp+=1
                else:
                    outp+=0
                #outp.append(sc)
            #print(j)
            if (outp>=1):
                corr_s[i,j] = 1
            else:
                corr_s[i,j] = -1
            progress_bar.next()
    progress_bar.finish()
    return corr_s
def stats_corr(corr):
    count_0 = 0
    count_1 = 0
    count_2 = 0
    count_3 = 0
    print(corr.shape)
    for i in range(0, corr.shape[0]):
        if (corr[i] == 0):
            count_0 += 1
        if (corr[i] == 1):
            count_1 += 1
        if (corr[i] == 2):
            count_2 += 1
        if (corr[i] == 3):
            count_3 += 1

    print("0: " + str(count_0))
    print("1: " + str(count_1))
    print("2: " + str(count_2))
    print("3: " + str(count_3))
def stats_corrs(corr_s):
    count_0 = 0
    count_1 = 0
    count_2 = 0
    count_3 = 0
    print(corr_s.shape)
    for i in range(0, corr_s.shape[0]):
        for j in range(0, corr_s.shape[1]):
            if (corr_s[i,j] == 0):
                count_0 += 1
            if (corr_s[i,j] == 1):
                count_1 += 1
            if (corr_s[i,j] == -1):
                count_2 += 1
    print("0: " + str(count_0))
    print("1: " + str(count_1))
    print("-1: " + str(count_2))
def means_from_file(file, plot = True):
    data = np.load(file)
    means_s = data['mean']
    if plot:
        fig = plt.figure()
        ax = p3.Axes3D(fig)
        ax.view_init(7, -80)
        ax.scatter(means_s[:, 0], means_s[:, 1], means_s[:, 2], color='r')
        plt.show()
    return means_s

def draw_registration_result(source, target, transformation):
    source_temp = copy.deepcopy(source)
    target_temp = copy.deepcopy(target)
    source_temp.paint_uniform_color([1, 0.706, 0])
    target_temp.paint_uniform_color([0, 0.651, 0.929])
    source_temp.transform(transformation)
    open3d.draw_geometries([source_temp, target_temp])

def render_online():
    vis = open3d.Visualizer()
    vis.create_window()
    vis.add_geometry(pcd)
    render_option = vis.get_render_option()
    render_option.point_size = 1
    to_reset_view_point = True
    #prev = get_one_point_cloud_turned(dataset, 0, take_each_n_point, centroid, rotated_centroid)
    for j in range(0, max_range):
        pc = get_one_point_cloud_turned(dataset, j, take_each_n_point, centroid, rotated_centroid)
        points = np.array(pc[:, :3])
        pcd.points = open3d.Vector3dVector(points)
        vis.update_geometry()
        if to_reset_view_point:
            vis.reset_view_point(True)
            to_reset_view_point = False
        vis.poll_events()
        vis.update_renderer()
        depth = vis.capture_depth_float_buffer(False)
        image = vis.capture_screen_float_buffer(False)
        # TODO: Save images to files
        plt.imsave("/home/kish/PycharmProjects/try/TestData/depth/{:05d}.png".format(j), \
                   np.asarray(depth), dpi=1)
        plt.imsave("/home/kish/PycharmProjects/try/TestData/image/{:05d}.png".format(j), \
                   np.asarray(image), dpi=1)
        time.sleep(0.2)


def render_online_filtered(filter_z = 0):
    vis = open3d.Visualizer()
    vis.create_window()
    pcd = open3d.PointCloud()
    vis.add_geometry(pcd)
    render_option = vis.get_render_option()
    render_option.point_size = 1
    to_reset_view_point = True
    # prev = get_one_point_cloud_turned(dataset, 0, take_each_n_point, centroid, rotated_centroid)
    for j in range(0, max_range):
        points = get_one_pcd_filtered(j,filter_z).points
        pcd.points = open3d.Vector3dVector(points)
        vis.update_geometry()
        if to_reset_view_point:
            vis.reset_view_point(True)
            to_reset_view_point = False
        vis.poll_events()
        vis.update_renderer()
        depth = vis.capture_depth_float_buffer(False)
        image = vis.capture_screen_float_buffer(False)
        # TODO: Save images to files
        plt.imsave("/home/kish/PycharmProjects/try/TestData/depth/{:05d}.png".format(j), \
                   np.asarray(depth), dpi=1)
        plt.imsave("/home/kish/PycharmProjects/try/TestData/image/{:05d}.png".format(j), \
                   np.asarray(image), dpi=1)
        time.sleep(0.2)


def render_online_segments(filter_z = 0):
    vis = open3d.Visualizer()
    vis.create_window()
    pcd = open3d.PointCloud()
    vis.add_geometry(pcd)
    render_option = vis.get_render_option()
    render_option.point_size = 10
    to_reset_view_point = True
    # prev = get_one_point_cloud_turned(dataset, 0, take_each_n_point, centroid, rotated_centroid)
    for j in range(0, max_range):
        pcds = get_one_clusters(get_one_pcd_filtered(j, filter_z))
        #points = get_one_pcd_filtered(j,filter_z).points
        #pcd.points = open3d.Vector3dVector(points)
        for f in range(0, len(pcds)):
            pcd.points = (pcds[f].points)

            #pcd.paint_uniform_color(pcds[f].paint_uniform_color)
            vis.update_geometry()
        if to_reset_view_point:
            vis.reset_view_point(True)
            to_reset_view_point = False
        vis.poll_events()
        vis.update_renderer()
        depth = vis.capture_depth_float_buffer(False)
        image = vis.capture_screen_float_buffer(False)
        # TODO: Save images to files
        plt.imsave("/home/kish/PycharmProjects/try/TestData/depth/{:05d}.png".format(j), \
                   np.asarray(depth), dpi=1)
        plt.imsave("/home/kish/PycharmProjects/try/TestData/image/{:05d}.png".format(j), \
                   np.asarray(image), dpi=1)
        time.sleep(0.2)

# TODO: Save images to video (clean)
def save_video():
    images = []
    path =  "/home/kish/PycharmProjects/try/TestData/image/"
    filenames = [f for f in listdir(path) if isfile(join(path, f))]
    with imageio.get_writer('/home/kish/PycharmProjects/try/TestData/depth/movie.gif', mode='I') as writer:
        for filename in filenames:
            image = imageio.imread('/home/kish/PycharmProjects/try/TestData/image/'+str(filename))
            writer.append_data(image)
def pairwise_registration(source, target):
    print("Apply point-to-plane ICP")
    icp_coarse = open3d.registration_icp(source, target,
            max_correspondence_distance_coarse, np.identity(4),
            open3d.TransformationEstimationPointToPlane())
    icp_fine = open3d.registration_icp(source, target,
            max_correspondence_distance_fine, icp_coarse.transformation,
            open3d.TransformationEstimationPointToPlane())
    transformation_icp = icp_fine.transformation
    information_icp = open3d.get_information_matrix_from_point_clouds(
            source, target, max_correspondence_distance_fine,
            icp_fine.transformation)
    return transformation_icp, information_icp
def get_one_pcd_filtered(i=0, filter_z = 0):
    pc = get_one_point_cloud_turned(dataset, i, take_each_n_point, centroid, rotated_centroid)
    #print(pc)
    filtered_pc = []
    for j in range (0, pc.shape[0]):
        if (pc[j,2]>filter_z):
            filtered_pc.append(pc[j])
    filtered_pc= np.array(filtered_pc).reshape(-1,3)
    #print(filtered_pc.shape)
    points = np.array(filtered_pc[:, :3])
    pcd = open3d.PointCloud()
    pcd.points = open3d.Vector3dVector(points)
    return pcd
def calc_prev_pcd(prev, pcd):
    vis = open3d.Visualizer()
    vis.create_window()
    vis.add_geometry(pcd)
    render_option = vis.get_render_option()
    render_option.point_size = 1
    to_reset_view_point = True
    pre = get_one_point_cloud_turned(dataset, 0, take_each_n_point, centroid, rotated_centroid)
    points = np.array(pre[:, :3])
    prev.points = open3d.Vector3dVector(points)
    for j in range(1, max_range):
        pc = get_one_point_cloud_turned(dataset, j, take_each_n_point, centroid, rotated_centroid)
        points = np.array(pc[:, :3])
        pcd.points = open3d.Vector3dVector(points)
        threshold = 0.02
        trans_init, info_init = pairwise_registration(pcd, prev)
        draw_registration_result(pcd, prev, trans_init)
        print("Initial alignment")
        evaluation = open3d.evaluate_registration(pcd, prev,
                                                  threshold, trans_init)
        print(evaluation)

        print("Apply point-to-point ICP")
        reg_p2p = open3d.registration_icp(pcd, prev, threshold, trans_init,
                                          open3d.TransformationEstimationPointToPoint())
        print(reg_p2p)
        print("Transformation is:")
        print(reg_p2p.transformation)
        print("")
        vis.update_geometry()
        if to_reset_view_point:
            vis.reset_view_point(True)
            to_reset_view_point = False
        vis.poll_events()

        vis.update_renderer(  draw_registration_result(pcd, prev, reg_p2p.transformation))
        image = vis.capture_screen_float_buffer(False)
        plt.imsave("/home/kish/PycharmProjects/try/TestData/pairwise/{:05d}.png".format(j), \
                   np.asarray(image), dpi=1)
        time.sleep(0.2)

        prev =  copy.deepcopy(pcd)
def execute_fast_global_registration(source_down, target_down,
        source_fpfh, target_fpfh, voxel_size):
    distance_threshold = voxel_size * 0.5
    print(":: Apply fast global registration with distance threshold %.3f" \
            % distance_threshold)
    result = open3d.registration_fast_based_on_feature_matching(
            source_down, target_down, source_fpfh, target_fpfh,
            open3d.FastGlobalRegistrationOption(
            maximum_correspondence_distance = distance_threshold))
def get_one_clusters(pcd, plot = False, algoritm = "Agl", number = 0):
    colors_arr = [[0,0,0], [0,0,1],[0,1,0],[0,1,1],[1,0,0],[1,0,1],[1,1,0],[1,1,1], [2,0,0], [2,0,1], [2,0,2], [2,1,0], [2,1,1], [2,1,2], [2,2,0],[2,2,1], [2,2,2], [3,0,0], [3,0,1], [3,0,2], [3,0,3],[3,1,0], [3,1,1],[3,1,2],[3,1,3],[3,2,0],[3,2,1],[3,2,2], [3,2,3]]
    pc = np.asarray(pcd.points)
    if (algoritm=="Agl"):
        ward = AgglomerativeClustering(clusters_per_pair, linkage='ward').fit(pc)
        label = ward.labels_
    elif (algoritm == "DBSCAN"):
        #weights = calc_weights(get_one_point_cloud_turned(dataset, number, take_each_n_point, centroid, rotated_centroid),trajectory[number])
        #weights = calc_weights(np.asanyarray(pcd.points),trajectory[number])
        db = DBSCAN(eps=1, min_samples=5).fit(pc)#, sample_weight= weights)
        label = db.labels_
        n_clusters_ = len(set(label)) - (1 if -1 in label else 0)
        n_noise_ = list(label).count(-1)
        print('Estimated number of clusters: %d' % n_clusters_)
        print('Estimated number of noise points: %d' % n_noise_)

    elif (algoritm == "Spectral"):
        clustering = SpectralClustering(n_clusters=clusters_per_pair, assign_labels = "discretize",
        random_state = 0).fit(pc)
        label = clustering.labels_
    else:
        print("not implemented error")
    pcds = []
    if (plot):
        fig = plt.figure()
        ax = p3.Axes3D(fig)
        for l in np.unique(label):
            if (l!=-1):
                ax.scatter(pc[label == l, 0], pc[label == l, 1], pc[label == l, 2],
                           color=plt.cm.jet(float(l) / np.max(label + 1)),
                           s=20, edgecolor='k')
                points = np.array(pc[label == l])
                pcd = open3d.PointCloud()
                pcd.points = open3d.Vector3dVector(points)
                pcds.append(pcd)
        plt.show()
    else:
        for l in np.unique(label):
            if (l != -1):
                points = np.array(pc[label == l])
                pcd = open3d.PointCloud()
                pcd.points = open3d.Vector3dVector(points)
                print(colors_arr[int(l)])
                pcd.paint_uniform_color(colors_arr[int(l)])

                pcds.append(pcd)
    return pcds
def cluster_all(j=2, plot = False):
    pcds_points = np.zeros((0,3))
    for i in range(0,j):
        pcds_points = np.vstack([pcds_points,np.asanyarray(get_one_pcd_filtered(i, 0.5).points)])
        #print(pcds_points.shape)
    ward = AgglomerativeClustering(clusters_per_pair, linkage='ward').fit(pcds_points)
    label = ward.labels_
    pcds = []
    if (plot):
        fig = plt.figure()
        ax = p3.Axes3D(fig)
        for l in np.unique(label):
            ax.scatter(pcds_points[label == l, 0], pcds_points[label == l, 1], pcds_points[label == l, 2],
                       color=plt.cm.jet(float(l) / np.max(label + 1)),
                       s=20, edgecolor='k')
            points = np.array(pcds_points[label == l])
            pcd = open3d.PointCloud()
            pcd.points = open3d.Vector3dVector(points)
            pcds.append(pcd)
        plt.show()
    pcds = np.array(pcds)
    return pcds

def custom_draw_geometry(j=0, saveF = True, filter_z = 0.5):
    vis = open3d.Visualizer()
    vis.create_window()
    pcds = get_one_clusters(get_one_pcd_filtered(0, filter_z))

    # open3d.draw_geometries(pcds)
    for i in range(0, len(pcds)):
        vis.add_geometry(pcds[i])
    if (j>0):
        for f in range(0,j):
            pcds = get_one_clusters(get_one_pcd_filtered(f, filter_z))

            # open3d.draw_geometries(pcds)
            #TODO: change labels!  change overloading
            for i in range (0, len(pcds)):
                vis.add_geometry(pcds[i])
            #vis.run()

            #vis.destroy_window()
            vis.poll_events()
            vis.update_renderer()
            image = vis.capture_screen_float_buffer(True)
            # TODO: Save images to files

            if (saveF):
                plt.imsave("/home/kish/PycharmProjects/try/TestData/image/{:05d}.png".format(f), \
                       np.asarray(image), dpi=1)

            time.sleep(0.2)
        vis.destroy_window()

def custom_draw_joint_geometry(pcds, saveF = False, number = 0, show = True, j = 0):
    vis = open3d.Visualizer()
    vis.create_window()

    # open3d.draw_geometries(pcds)
    for i in range(0, len(pcds)):
        vis.add_geometry(pcds[i])
    #pcds = get_one_clusters(get_one_pcd_filtered(f, filter_z))

    # open3d.draw_geometries(pcds)
    # TODO: change labels!  change overloading
    # vis.run()

    # vis.destroy_window()
    vis.poll_events()
    vis.reset_view_point(True)
    vis.get_render_option()
    vis.update_renderer()
    #ctr = vis.get_view_control()
    image = vis.capture_screen_float_buffer(True)
    # TODO: Save images to files

    if (saveF):
        plt.imsave("/home/kish/PycharmProjects/try/TestData/new/{:05d}.png".format(number), \
                   np.asarray(image), dpi=1)
    if(show):
        vis.run()
        vis.destroy_window()


def pairwise_registration(source, target):
    print("Apply point-to-plane ICP")
    icp_coarse = open3d.registration_icp(source, target,
            max_correspondence_distance_coarse, np.identity(4),
            open3d.TransformationEstimationPointToPlane())
    icp_fine = open3d.registration_icp(source, target,
            max_correspondence_distance_fine, icp_coarse.transformation,
            open3d.TransformationEstimationPointToPlane())
    transformation_icp = icp_fine.transformation
    information_icp = open3d.get_information_matrix_from_point_clouds(
            source, target, max_correspondence_distance_fine,
            icp_fine.transformation)
    return transformation_icp, information_icp


def full_registration(pcds,
        max_correspondence_distance_coarse, max_correspondence_distance_fine):
    pose_graph = open3d.PoseGraph()
    odometry = np.identity(4)
    pose_graph.nodes.append(open3d.PoseGraphNode(odometry))
    n_pcds = len(pcds)
    for source_id in range(n_pcds):
        for target_id in range(source_id + 1, n_pcds):
            transformation_icp, information_icp = pairwise_registration(
                    pcds[source_id], pcds[target_id])
            print("Build PoseGraph")
            if target_id == source_id + 1: # odometry case
                odometry = np.dot(transformation_icp, odometry)
                pose_graph.nodes.append(open3d.PoseGraphNode(np.linalg.inv(odometry)))
                print(odometry)
                pose_graph.edges.append(open3d.PoseGraphEdge(source_id, target_id,
                        transformation_icp, information_icp, uncertain = False))
            else: # loop closure case
                pose_graph.edges.append(open3d.PoseGraphEdge(source_id, target_id,
                        transformation_icp, information_icp, uncertain = True))
    return pose_graph
def get_joint_segments(pcds, pcds1, plot = False,  filter_z = 0.5):
    pairs = np.zeros((len(pcds), len(pcds1)))
    pcds_joint = []
    for i in range(0, len(pcds)):
        for j in range(0, len(pcds1)):
            pairs[i, j] = str(pairwise_icp(pcds[i], pcds1[j], filter_z, draw=False))
            if (pairs[i,j]>0.3):
                # join segments +down_sample+draw
                #TODO: add downsample, add pcds output and full render
                pcd_joint = [pcds[i], pcds1[j]]
                pcd_combined = open3d.PointCloud()
                for point_id in range(len(pcd_joint)):
                    #pcds[point_id].transform(pose_graph.nodes[point_id].pose)
                    pcd_combined += pcd_joint[point_id]

                pcd_combined_down = open3d.voxel_down_sample(pcd_combined, voxel_size=0.0001)
                # open3d.write_point_cloud("multiway_registration.pcd", pcd_combined_down)
                #open3d.draw_geometries([pcd_combined_down])
                #TODO: add posegraph combination
                pcds_joint.append(pcd_combined_down)
                if (plot):
                    open3d.draw_geometries(pcd_combined_down)
    #print(pairs)
    segments =  []
    for i in range(0, pairs.shape[1]):
        segment_size = 0
        for j in range(0, pairs.shape[0]):
            if (pairs[j,i]>0.5):
                segment_size+=1
                if (plot):
                    (pairwise_icp(pcds[i], pcds1[j], filter_z, draw=True))
        segments.append(segment_size)
        #join segments here

        #render full image
        #save images of full pcd
    return pairs, np.array(segments), pcds_joint
def get_joint_pairs(pcds, pcds1, plot = False,  filter_z = 0.5):
    pairs = np.zeros((len(pcds), len(pcds1)))
    pcds_joint = []
    for i in range(0, len(pcds)):
        for j in range(0, len(pcds1)):
            pairs[i, j] = str(pairwise_icp(pcds[i], pcds1[j], filter_z, draw=False))
            if (pairs[i,j]>0.5):
                # join segments +down_sample+draw
                #TODO: add downsample, add pcds output and full render
                pcd_joint = [pcds[i], pcds1[j]]
                pcd_combined = open3d.PointCloud()
                for point_id in range(len(pcd_joint)):
                    #pcds[point_id].transform(pose_graph.nodes[point_id].pose)
                    pcd_combined += pcd_joint[point_id]

                pcd_combined_down = open3d.voxel_down_sample(pcd_combined, voxel_size=0.0001)
                # open3d.write_point_cloud("multiway_registration.pcd", pcd_combined_down)
                #open3d.draw_geometries([pcd_combined_down])
                #TODO: add posegraph combination
                pcds_joint.append(pcd_combined_down)
                if (plot):
                    open3d.draw_geometries(pcd_combined_down)
    for i in range(0, pairs.shape[0]):
        if (pairs[i].min() == 0):
            pcds_joint.append(pcds[i])
    for i in range(0, pairs.shape[1]):
        if (pairs[:,i].min() == 0):
            pcds_joint.append(pcds1[i])
    return pairs, pcds_joint

def calc_weights(new_pcd, center):
    #new_pcd = get_one_point_cloud_turned(dataset,0,1,centroid, rotated_centroid)
    #r = np.array([(new_pcd[:,0].max()-new_pcd[:,0].min())/new_pcd.shape[0],(new_pcd[:,1].max()-new_pcd[:,1].min())/new_pcd.shape[0],(new_pcd[:,2].max()-new_pcd[:,2].min())/new_pcd.shape[0] ])
    #print(r)
    #center = trajectory[0]
    #trashold = r/2
    distances = []
    for i in range(0, new_pcd.shape[0]):
        distances.append(np.linalg.norm(new_pcd[i] - center))
    distances = np.array(distances)
    #plt.figure()
    #plt.hist(distances)
    #plt.show()
    #plt.figure()
    #plt.plot(distances, range(0, distances.shape[0]), '.g')
    #min_max_scaler = preprocessing.MinMaxScaler()
    X = distances
    X_std = (X - X.min(axis=0)) / (X.max(axis=0) - X.min(axis=0))
    X_scaled = X_std * (X.max() - X.min()) + X.min()
    distances = np.array(X_scaled/X.max())
    #plt.plot(distances,range(0,distances.shape[0]), '.r')
    #distances_new = distances-distances.max()
    #distances_new = (distances_new-distances_new.min())/(-1*distances_new.min())
    #plt.plot(distances_new, range(0, distances_new.shape[0]), '.b')
    #plt.show()
    return distances
def calc_weights_new(new_pcd, center):
    #new_pcd = get_one_point_cloud_turned(dataset,0,1,centroid, rotated_centroid)
    r = np.array([(new_pcd[:,0].max()-new_pcd[:,0].min())/new_pcd.shape[0],(new_pcd[:,1].max()-new_pcd[:,1].min())/new_pcd.shape[0],(new_pcd[:,2].max()-new_pcd[:,2].min())/new_pcd.shape[0] ])
    #print(r)
    #center = trajectory[0]
    trashold = r/2
    distances = []
    for i in range(0, new_pcd.shape[0]):
        distances.append(np.linalg.norm(new_pcd[i] - center))
    distances = np.array(distances)
    print(distances.max())
    print(r)
    finish = (distances.max()-center)/r
    print(finish)
    #calc current weight step by step
    cur_step = center
    print(center)
    weights = []
    i = 0
    go = True
    while (go):
        weights.append(i)
        i+=1
        cur_step+=r
        if((cur_step[0,0]>=finish[0,0])and(cur_step[0,1]>=finish[0,1])and(cur_step[0,2]>=finish[0,2])):
            go = False
    print(weights)
    #plt.figure()
    #plt.hist(distances)
    #plt.show()

    #min_max_scaler = preprocessing.MinMaxScaler()
    X = distances
    X_std = (X - X.min(axis=0)) / (X.max(axis=0) - X.min(axis=0))
    X_scaled = X_std * (X.max() - X.min()) + X.min()
    distances = np.array(X_scaled/X.max())

    return distances

def pairwise_icp(pcd1, pcd2, threshold, draw = False):
    open3d.set_verbosity_level(open3d.VerbosityLevel.Debug)
    # pcds_down = load_point_clouds(voxel_size)
    trans_init = np.asarray(
        [[1., 0., 0., 0.],
         [0., 1., 0., 0.],
         [0., 0., 1., 0.],
         [0.0, 0.0, 0.0, 1.0]])
    #pcd1_down = open3d.voxel_down_sample(pcd1, voxel_size=voxel_size)
    #pcd2_down = open3d.voxel_down_sample(pcd2, voxel_size=voxel_size)
    #pcds_down = [pcd1_down, pcd2_down]
    pcd1_down = pcd1
    pcd2_down = pcd2
    evaluation = open3d.evaluate_registration(pcd1_down, pcd2_down,
                                       threshold, trans_init)
    #print(evaluation)
    reg_p2p = open3d.registration_icp(pcd1_down, pcd2_down, threshold, trans_init,
                               open3d.TransformationEstimationPointToPoint())
    if (draw):
        draw_registration_result(pcd1_down, pcd2_down, reg_p2p.transformation)
    #open3d.draw_geometries(pcds_down)
    '''
    print("Full registration ...")
    pose_graph = full_registration(pcds_down,
                                   max_correspondence_distance_coarse,
                                   max_correspondence_distance_fine)

    print("Optimizing PoseGraph ...")
    option = open3d.GlobalOptimizationOption(
        max_correspondence_distance=max_correspondence_distance_fine,
        edge_prune_threshold=0.25,
        reference_node=0)
    open3d.global_optimization(pose_graph,
                               open3d.GlobalOptimizationLevenbergMarquardt(),
                               open3d.GlobalOptimizationConvergenceCriteria(), option)

    print("Transform points and display")
    for point_id in range(len(pcds_down)):
        print(pose_graph.nodes[point_id].pose)
        pcds_down[point_id].transform(pose_graph.nodes[point_id].pose)
    #open3d.draw_geometries(pcds_down)

    print("Make a combined point cloud")
    pcds = [pcd1, pcd2]
    pcd_combined = open3d.PointCloud()
    for point_id in range(len(pcds)):
        pcds[point_id].transform(pose_graph.nodes[point_id].pose)
        pcd_combined += pcds[point_id]

    pcd_combined_down = open3d.voxel_down_sample(pcd_combined, voxel_size=voxel_size)
    #open3d.write_point_cloud("multiway_registration.pcd", pcd_combined_down)
    open3d.draw_geometries([pcd_combined_down])
    numb = len(pcd_combined.points)/len(pcd_combined_down.points)
    
    return numb
    '''
    return evaluation.fitness

np.set_printoptions(precision=4, suppress=True)

# Folder with data set
basedir = '/media/kish/CHANGE/dataset'
# Sequence to use
sequence = '00'
# Amount of frames to download.
max_range = 100
# How frequently should we select point clouds
pcs_step = 1
# Get n points from each of point clouds
take_each_n_point = 10

# Load odometry and point clouds
dataset = pykitti.odometry(basedir, sequence, frames=range(0, max_range, 1))

# Plot this

f2 = plt.figure()
ax2 = f2.add_subplot(111, projection='3d')

trajectory = get_trajectory(dataset)

trajectory, centroid, rotated_centroid, M = find_best_fitting_plane(trajectory, ax2)

pc_s, shape_s = get_point_cloud(dataset, pcs_step, take_each_n_point, ax2)
print(shape_s)
ax2.scatter(trajectory[:, 0],
            trajectory[:, 1],
            trajectory[:, 2],
            c='red')

pc_s -= centroid

pc_s = pc_s[:, :] * M

pc_s += rotated_centroid

pcs_step_cl = 20
clusters_per_pair = 10
voxel_size = 0.5
max_correspondence_distance_coarse = voxel_size * 15
max_correspondence_distance_fine = voxel_size * 1.5
pcd = open3d.PointCloud()
prev = open3d.PointCloud()



#render_online()
#calc_prev_pcd(prev, pcd)
#open3d.draw_geometries([get_one_pcd_filtered(0,0)])
#render_online_filtered(filter_z=0)
#pcds = get_one_clusters(get_one_pcd_filtered(0,0.5), plot=True)
#get_joint_segments(0,1)
#pairwise_icp(pcds[0],pcds1[1], 0.5)
#open3d.draw_geometries(pcds)


#custom_draw_geometry(j=200,filter_z=0.5)
#(calc_weights(get_one_point_cloud_turned(dataset, 1,take_each_n_point,centroid, rotated_centroid),trajectory[1]))
#pcds = get_one_clusters(get_one_pcd_filtered(1,0.5), plot=True, algoritm="DBSCAN", number=1)
#pcd1 = get_one_pcd_filtered(0, filter_z=0.5)
#pcd2 = get_one_pcd_filtered(1, filter_z=0.5)
#pcd1.paint_uniform_color([1,0,0])
#pcd2.paint_uniform_color([0,1,0])

#open3d.draw_geometries([pcd1, pcd2])
#print(pcd1)
def pairs_minimized(a,b,algoritm, show = False):
    pcds = get_one_clusters(get_one_pcd_filtered(a, filter_z=0.5), algoritm=algoritm, number=a)
    for i in range(a, b):
        pcds1 = copy.deepcopy(get_one_clusters(get_one_pcd_filtered(i + 1, filter_z=0.5), algoritm=algoritm, number=i))
        pairs, sizes, pcds = (get_joint_segments(pcds, pcds1, plot=False))
        # vis = open3d.Visualizer()
        # vis.create_window()
        # pcd = open3d.PointCloud()
        # open3d.draw_geometries(pcds)
        # for i in range(0, len(pcds)):

        # for i in range(0, len(pcds)):
        #    vis.add_geometry(pcd)
        #    pcd.points = copy.deepcopy(open3d.Vector3dVector(pcds[i].points))
        # pcd.paint_uniform_color(pcds[i].paint_uniform_color)
        #    vis.update_geometry()
        # vis.poll_events()
        # vis.update_renderer()
        # time.sleep(0.2)
        # for 1 render
        custom_draw_joint_geometry(pcds, saveF=True, number=i, show = show)
        pcds = copy.deepcopy(pcds1)
        # pcd1 = open3d.PointCloud()
        pcd1 = get_one_pcd_filtered(i, filter_z=0.5)
        pcd1.paint_uniform_color([5, 5, 5])
        # pcd1 = open3d.PointCloud()
        pcd2 = get_one_pcd_filtered(i + 1, filter_z=0.5)
        pcd2.paint_uniform_color([9, 9, 9])
        # pcds.append(pcd1)
        # pcds.append(pcd2)
        # for one render with the scene "before"
        # open3d.draw_geometries(pcds)


def pairs_maximized(a,b, algoritm, show = False):
    pcds = get_one_clusters(get_one_pcd_filtered(a, filter_z=0.5), algoritm=algoritm, number=a)
    pcds1 = copy.deepcopy(get_one_clusters(get_one_pcd_filtered(a + 1, filter_z=0.5), algoritm=algoritm, number=a+1))
    _, _, pcds_out_prev = (get_joint_segments(pcds, pcds1, plot=False))
    custom_draw_joint_geometry(pcds_out_prev, saveF=True, number=a, show=show)
    for i in range(a+2,b,2):

        pcds = get_one_clusters(get_one_pcd_filtered(i, filter_z=0.5), algoritm=algoritm, number=i)
        pcds1 = copy.deepcopy(get_one_clusters(get_one_pcd_filtered(i + 1, filter_z=0.5), algoritm=algoritm, number=i+1))
        _,_, pcds_out = (get_joint_segments(pcds, pcds1, plot=False))
        #custom_draw_joint_geometry(pcds_out, saveF=True, number=i)
        _,pcds_out_prev = get_joint_pairs(pcds_out,pcds_out_prev)
        #print(pcds_out_prev)
        custom_draw_joint_geometry(pcds_out_prev, saveF=True, number=i+1, show= show)

pairs_maximized(0,20, algoritm="DBSCAN", show=False)
#pairs_minimized(0,5, "DBSCAN", show = False)
#calc_weights(get_one_point_cloud_turned(dataset, 0, take_each_n_point, centroid, rotated_centroid), trajectory[0])

#TODO - adopt for sequences, step by step. Improve weights, play with parameters, solve different number of segments, play with number of segments, improve visualisation
#render_online_segments(0.5)