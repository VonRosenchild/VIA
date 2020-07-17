import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, csgraph
import scipy
import igraph as ig
import leidenalg
import time
import hnswlib
import matplotlib.pyplot as plt
import matplotlib
import math
import multiprocessing
from scipy.sparse.csgraph import minimum_spanning_tree
from scipy import sparse
from sklearn.metrics.pairwise import euclidean_distances
import umap
import scanpy as sc
from MulticoreTSNE import MulticoreTSNE as TSNE
import random
from scipy.sparse.csgraph import connected_components
import pygam as pg
import matplotlib.colors as colors
import matplotlib.cm as cm
import palantir  # /home/shobi/anaconda3/envs/ViaEnv/lib/python3.7/site-packages/palantir
from termcolor import colored
import seaborn as sns


# for EB data, def get_full_paths() graph has 4 NN instead of 3NN and we revise the path to remove clusters that are only visited once (noisy)

# jan2020 Righclick->GIT->Repository-> PUSH
def plot_sc_pb(ax, embedding, prob, ti):
    # threshold = #np.percentile(prob, 95)#np.mean(prob) + 3 * np.std(prob)
    # print('thresold', threshold, np.max(prob))
    # prob = [x if x < threshold else threshold for x in prob]
    prob = np.sqrt(prob)  # scale values to improve visualization of colors
    cmap = matplotlib.cm.get_cmap('viridis')
    norm = matplotlib.colors.Normalize(vmin=0, vmax=np.max(prob))
    prob = np.asarray(prob)
    print('prob plot stats (min, max, mean)', min(prob), max(prob), np.mean(prob))
    # changing the alpha transapency parameter for plotting points
    c = cmap(norm(prob))
    c = c.reshape(-1, 4)
    loc_c = np.where(prob <= 0.3)[0]
    c[loc_c, 3] = 0.2
    loc_c = np.where((prob > 0.3) & (prob <= 0.5))[0]
    c[loc_c, 3] = 0.5
    loc_c = np.where((prob > 0.5) & (prob <= 0.7))[0]
    c[loc_c, 3] = 0.8
    loc_c = np.where((prob > 0.7))[0]
    c[loc_c, 3] = 0.8
    ax.scatter(embedding[:, 0], embedding[:, 1], c=c, s=10, cmap='viridis',
               edgecolors='none')
    ax.set_title('Target: ' + str(ti))


def simulate_multinomial(vmultinomial):
    r = np.random.uniform(0.0, 1.0)
    CS = np.cumsum(vmultinomial)
    CS = np.insert(CS, 0, 0)
    m = (np.where(CS < r))[0]
    nextState = m[len(m) - 1]
    return nextState


def sc_loc_ofsuperCluster_PCAspace(p0, p1, idx):
    # ci_list: single cell location of average location of supercluster based on embedded space hnsw
    # Returns location (index) in unsampled PCA space of the location of the super-cluster or sub-terminal-cluster and root
    print("dict of terminal state pairs, Super: sub: ", p1.dict_terminal_super_sub_pairs)
    p0_labels = np.asarray(p0.labels)
    p1_labels = np.asarray(p1.labels)
    p1_sc_markov_pt = p1.single_cell_pt_markov
    ci_list = []
    for ci in list(set(p0.labels)):
        if ci in p1.revised_super_terminal_clusters:  # p0.terminal_clusters:
            loc_i = np.where(p1_labels == p1.dict_terminal_super_sub_pairs[ci])[0]
            # loc_i = np.where(p0_labels == ci)[0]
            # val_pt = [p1.single_cell_pt_markov[i] for i in loc_i]
            val_pt = [p1_sc_markov_pt[i] for i in loc_i]
            th_pt = np.percentile(val_pt, 0)  # 80
            loc_i = [loc_i[i] for i in range(len(val_pt)) if val_pt[i] >= th_pt]
            temp = np.mean(p0.data[loc_i], axis=0)
            labelsq, distances = p0.knn_struct.knn_query(temp, k=1)
            ci_list.append(labelsq[0][0])

        elif ci in p0.root:
            loc_root = np.where(np.asarray(p0.root) == ci)[0][0]
            # print('loc root', loc_root)
            p1_root_label = p1.root[loc_root]
            loc_i = np.where(np.asarray(p1_labels) == p1_root_label)[0]
            # print('loc_i', loc_i)
            # print('len p1')
            # loc_i = np.where(p0.labels == ci)[0]
            val_pt = [p1_sc_markov_pt[i] for i in loc_i]
            th_pt = np.percentile(val_pt, 20)  # 50
            loc_i = [loc_i[i] for i in range(len(val_pt)) if val_pt[i] <= th_pt]
            temp = np.mean(p0.data[loc_i], axis=0)
            labelsq, distances = p0.knn_struct.knn_query(temp, k=1)
            ci_list.append(labelsq[0][0])
        else:
            # loc_i = np.where(np.asarray(p0.labels) == ci)[0]
            loc_i = np.where(p0_labels == ci)[0]
            temp = np.mean(p0.data[loc_i], axis=0)
            labelsq, distances = p0.knn_struct.knn_query(temp, k=1)
            ci_list.append(labelsq[0][0])

        X_ds = p0.data[idx]
        p_ds = hnswlib.Index(space='l2', dim=p0.data.shape[1])
        p_ds.init_index(max_elements=X_ds.shape[0], ef_construction=200, M=16)
        p_ds.add_items(X_ds)
        p_ds.set_ef(50)

        new_superclust_index_ds = []
        for item in ci_list:
            labelsq, distances = p_ds.knn_query(p0.data[item, :], k=1)
            new_superclust_index_ds.append(labelsq[0][0])
    return new_superclust_index_ds


def sc_loc_ofsuperCluster_embeddedspace(embedding, p0, p1, idx):
    # ci_list: single cell location of average location of supercluster based on embedded space hnsw
    # idx is the indices of the subsampled elements
    print("dict of terminal state pairs, Super: sub: ", p1.dict_terminal_super_sub_pairs)
    knn_hnsw = hnswlib.Index(space='l2', dim=embedding.shape[1])
    knn_hnsw.init_index(max_elements=embedding.shape[0], ef_construction=200, M=16)
    knn_hnsw.add_items(embedding)
    knn_hnsw.set_ef(50)
    p0_labels = np.asarray(p0.labels)[idx]
    p1_labels = np.asarray(p1.labels)[idx]
    p1_sc_markov_pt = list(np.asarray(p1.single_cell_pt_markov)[idx])
    p0_sc_markov_pt = list(np.asarray(p0.single_cell_pt_markov)[idx])
    ci_list = []
    ci_dict = {}
    # for ci in list(set(p0.labels)):

    for ci in list(set(p0_labels)):

        if ci in p1.revised_super_terminal_clusters:  # p0.terminal_clusters:
            print('ci is in ', ci, 'terminal clus')
            loc_i = np.where(p1_labels == p1.dict_terminal_super_sub_pairs[ci])[0]
            # loc_i = np.where(p0_labels == ci)[0]
            # val_pt = [p1.single_cell_pt_markov[i] for i in loc_i]
            val_pt = [p1_sc_markov_pt[i] for i in loc_i]
            th_pt = np.percentile(val_pt, 80)  # 50
            loc_i = [loc_i[i] for i in range(len(val_pt)) if val_pt[i] >= th_pt]
            x = [embedding[xi, 0] for xi in loc_i]
            y = [embedding[yi, 1] for yi in loc_i]
        elif ci in p0.root:

            if len(p0.root) > 1:
                print('ci is in ', ci, 'Root')
                loc_i = np.where(p0_labels == ci)[0]
                val_pt = [p0_sc_markov_pt[i] for i in loc_i]
            else:
                loc_root = np.where(np.asarray(p0.root) == ci)[0][0]
                # print('loc root', loc_root)
                p1_root_label = p1.root[loc_root]
                loc_i = np.where(np.asarray(p1_labels) == p1_root_label)[0]
                val_pt = [p1_sc_markov_pt[i] for i in loc_i]
                # print('loc_i', loc_i)
                # print('len p1')

            th_pt = np.percentile(val_pt, 20)  # 50
            loc_i = [loc_i[i] for i in range(len(val_pt)) if val_pt[i] <= th_pt]
            x = [embedding[xi, 0] for xi in loc_i]
            y = [embedding[yi, 1] for yi in loc_i]
        else:
            print('ci is in ', ci, 'not root , not terminal clus')
            # loc_i = np.where(np.asarray(p0.labels) == ci)[0]
            loc_i = np.where(p0_labels == ci)[0]
            # temp = np.mean(adata_counts.obsm['X_pca'][:, 0:ncomps][loc_i], axis=0)
            x = [embedding[xi, 0] for xi in loc_i]
            y = [embedding[yi, 1] for yi in loc_i]

        labelsq, distancesq = knn_hnsw.knn_query(np.array([np.mean(x), np.mean(y)]), k=1)
        # labels, distances = p.knn_query(temp, k=1)
        ci_list.append(labelsq[0][0])
        ci_dict[ci] = labelsq[0][0]
        print('sc_loc nn clusterp0', ci, np.mean(x), np.mean(y))
        print(embedding[labelsq[0][0], 0], embedding[labelsq[0][0], 1])
    return knn_hnsw, ci_dict


def draw_sc_evolution_trajectory_dijkstra(p1, embedding, knn_hnsw, G, idx, X_data):
    # G is the igraph knn (low K) used for shortest path in high dim space. no idx needed as it's made on full sample
    # knn_hnsw is the knn made in the embedded space used for query to find the nearest point in the downsampled embedding
    #   that corresponds to the single cells in the full graph
    # X_data is the PCA space with all samples
    # idx is the selected indices of the downsampled samples
    y_root = []
    x_root = []
    root1_list = []
    p1_sc_bp = p1.single_cell_bp[idx, :]
    p1_labels = np.asarray(p1.labels)[idx]
    p1_sc_pt_markov = list(np.asarray(p1.single_cell_pt_markov)[idx])
    p1_cc = p1.connected_comp_labels

    X_ds = X_data[idx, :]
    p_ds = hnswlib.Index(space='l2', dim=X_ds.shape[1])
    p_ds.init_index(max_elements=X_ds.shape[0], ef_construction=200, M=16)
    p_ds.add_items(X_ds)
    p_ds.set_ef(50)

    for ii, r_i in enumerate(p1.root):
        loc_i = np.where(p1_labels == p1.root[ii])[0]
        x = [embedding[xi, 0] for xi in loc_i]
        y = [embedding[yi, 1] for yi in loc_i]

        labels_root, distances_root = knn_hnsw.knn_query(np.array([np.mean(x), np.mean(y)]),
                                                         k=1)  # sc location in embedded space of root cell
        x_root.append(embedding[labels_root, 0][0])
        y_root.append(embedding[labels_root, 1][0])

        labelsroot1, distances1 = p1.knn_struct.knn_query(X_ds[labels_root[0][0], :],
                                                          k=1)  # index of sc-root-cell in the full-PCA space. Need for path

        root1_list.append(labelsroot1[0][0])

    # single-cell branch probability evolution probability
    for i, ti in enumerate(p1.terminal_clusters):
        # print('i, ti, p1.root, p1.connected', i, ti, p1.root, p1_cc)
        # print('root1list', root1_list)
        root_i = p1.root[p1_cc[ti]]
        xx_root = x_root[p1_cc[ti]]
        yy_root = y_root[p1_cc[ti]]
        fig, ax = plt.subplots()
        plot_sc_pb(ax, embedding, p1_sc_bp[:, i], ti)

        loc_i = np.where(p1_labels == ti)[0]
        val_pt = [p1_sc_pt_markov[i] for i in loc_i]
        th_pt = np.percentile(val_pt, 50)  # 50
        loc_i = [loc_i[i] for i in range(len(val_pt)) if val_pt[i] >= th_pt]
        x = [embedding[xi, 0] for xi in
             loc_i]  # location of sc nearest to average location of terminal clus in the EMBEDDED space
        y = [embedding[yi, 1] for yi in loc_i]
        labels, distances = knn_hnsw.knn_query(np.array([np.mean(x), np.mean(y)]),
                                               k=1)  # knn_hnsw is knn of embedded space
        x_sc = embedding[labels[0], 0]  # terminal sc location in the embedded space
        y_sc = embedding[labels[0], 1]
        start_time = time.time()
        labelsq1, distances1 = p1.knn_struct.knn_query(X_ds[labels[0][0], :],
                                                       k=1)  # find the nearest neighbor in the PCA-space full graph
        print('labels root and labels[0]', root1_list[p1_cc[ti]], labels[0])
        ## path = G.get_shortest_paths(labels_root[0][0], to=labels[0][0], weights='weight') #G is the knn of all sc points
        # path = G.get_shortest_paths(labelsroot1[0][0], to=labelsq1[0][0], weights='weight')  # G is the knn of all sc points
        path = G.get_shortest_paths(root1_list[p1_cc[ti]], to=labelsq1[0][0])  # weights='weight')
        # G is the knn of all sc points

        path_idx = []  # find the single-cell which is nearest to the average-location of a terminal cluster
        # get the nearest-neighbor in this downsampled PCA-space graph. These will make the new path-way points
        path = path[0]

        print(f"get_shortest_paths time: {time.time()-start_time}")
        print('paths sc indices', path)
        # clusters of path
        cluster_path = []
        for cell_ in path:
            cluster_path.append(p1.labels[cell_])
            # , round(p1.single_cell_pt_markov[cl],1)])
        print(colored('cluster_path', 'green'), colored('terminal state: ', 'blue'), ti, cluster_path)
        revised_cluster_path = []
        revised_sc_path = []
        for enum_i, clus in enumerate(cluster_path):
            num_instances_clus = cluster_path.count(clus)
            if (clus == cluster_path[0]) | (clus == cluster_path[-1]):
                revised_cluster_path.append(clus)
                revised_sc_path.append(path[enum_i])
            else:
                if num_instances_clus > 1:
                    revised_cluster_path.append(clus)
                    revised_sc_path.append(path[enum_i])
        print(colored('cluster_path_revised', 'green'), colored('terminal state: ', 'blue'), ti, revised_cluster_path)
        print(colored('sc_path_revised', 'green'), colored('terminal state: ', 'blue'), ti, revised_sc_path)
        path = revised_sc_path  # (based on hi-dim PCA KNN)

        for pii in path:
            labelsq, distances = p_ds.knn_query(X_data[pii, :], k=1)
            # print('location of pathway point in downsampled idx-space', labelsq[0][0])
            path_idx.append(labelsq[0][0])

        downsampled_cluster_idx = []
        for clus_ in path_idx:
            downsampled_cluster_idx.append(p1.labels[clus_])
        print(colored('clusters on path in embedded space', 'red'), downsampled_cluster_idx)

        path = path_idx
        n_orange = len(path)
        orange_m = np.zeros((n_orange, 3))
        for enum_point, point in enumerate(path):
            # ax.text(embedding[point, 0], embedding[point, 1], 'D ' + str(enum_point), color='blue', fontsize=8)
            orange_m[enum_point, 0] = embedding[point, 0]
            orange_m[enum_point, 1] = embedding[point, 1]
            orange_m[enum_point, 2] = p1_sc_pt_markov[point]
        from sklearn.neighbors import NearestNeighbors
        k_orange = 3  # increasing can smoothen in simple trajectories (Toy)
        nbrs = NearestNeighbors(n_neighbors=k_orange, algorithm='ball_tree').fit(
            orange_m[:, 0:])  # make a knn in low-dim space using points of path in embedded space
        distances, indices = nbrs.kneighbors(orange_m[:, 0:])
        row_list = []
        col_list = []
        dist_list = []

        for i_or in range(n_orange):
            for j_or in range(1, k_orange):
                row_list.append(i_or)
                col_list.append(indices[i_or, j_or])
                dist_list.append(distances[i_or, j_or])
        print('target number ' + str(ti))

        orange_adjacency_knn = csr_matrix((np.array(dist_list), (np.array(row_list), np.array(col_list))),
                                          shape=(n_orange, n_orange))
        print('orange adj knn shape', orange_adjacency_knn.shape)

        n_mst, comp_labels_mst = connected_components(csgraph=orange_adjacency_knn, directed=False, return_labels=True)

        for enum_point, point in enumerate(path):  # [0]):
            orange_m[enum_point, 2] = p1_sc_pt_markov[point] * p1_sc_pt_markov[
                point] * 2  # p1.single_cell_pt_markov[point] * p1.single_cell_pt_markov[point]*2

        while n_mst > 1:
            comp_root = comp_labels_mst[0]
            # print('comp-root', comp_root)
            min_ed = 9999999
            loc_comp_i = np.where(comp_labels_mst == comp_root)[0]
            loc_comp_noti = np.where(comp_labels_mst != comp_root)[0]
            # print('compi', loc_comp_i)
            # print('comp_noti', loc_comp_noti)
            orange_pt_val = [orange_m[cc, 2] for cc in loc_comp_i]
            loc_comp_i_revised = [loc_comp_i[cc] for cc in range(len(orange_pt_val)) if
                                  orange_pt_val[cc] >= np.percentile(orange_pt_val, 70)]

            for nn_i in loc_comp_i_revised:

                ed = euclidean_distances(orange_m[nn_i, :].reshape(1, -1), orange_m[loc_comp_noti])

                if np.min(ed) < min_ed:
                    ed_where_min = np.where(ed[0] == np.min(ed))[0][0]
                    # print('ed where min', ed_where_min, np.where(ed[0] == np.min(ed)))
                    min_ed = np.min(ed)
                    ed_loc_end = loc_comp_noti[ed_where_min]
                    ed_loc_start = nn_i
            # print('min ed', min_ed)
            print('Connecting components before sc-bp-GAM: the closest pair of points', ed_loc_start, ed_loc_end)
            orange_adjacency_knn[ed_loc_start, ed_loc_end] = min_ed
            n_mst, comp_labels_mst = connected_components(csgraph=orange_adjacency_knn, directed=False,
                                                          return_labels=True)

        if n_mst == 1:  # if no disconnected components in the graph #now draw the shortest path along the knn of embedding points along the path

            (orange_sources, orange_targets) = orange_adjacency_knn.nonzero()
            orange_edgelist = list(zip(orange_sources.tolist(), orange_targets.tolist()))

            G_orange = ig.Graph(n=orange_adjacency_knn.shape[0], edges=orange_edgelist,
                                edge_attrs={'weight': orange_adjacency_knn.data.tolist()}, )
            path_orange = G_orange.get_shortest_paths(0, to=orange_adjacency_knn.shape[0] - 1, weights='weight')[0]
            print('path orange', path_orange)
            len_path_orange = len(path_orange)

            for path_i in range(len_path_orange - 1):
                path_x_start = orange_m[path_orange[path_i], 0]
                path_x_end = orange_m[path_orange[path_i + 1], 0]
                orange_x = [orange_m[path_orange[path_i], 0], orange_m[path_orange[path_i + 1], 0]]
                orange_minx = min(orange_x)
                orange_maxx = max(orange_x)

                orange_y = [orange_m[path_orange[path_i], 1], orange_m[path_orange[path_i + 1], 1]]
                orange_miny = min(orange_y)
                orange_maxy = max(orange_y)
                orange_embedding_sub = embedding[
                    ((embedding[:, 0] <= orange_maxx) & (embedding[:, 0] >= orange_minx)) & (
                            (embedding[:, 1] <= orange_maxy) & ((embedding[:, 1] >= orange_miny)))]

                if (orange_maxy - orange_miny > 5) | (orange_maxx - orange_minx > 5):
                    orange_n_reps = 150
                else:
                    orange_n_reps = 100
                or_reps = np.repeat(np.array([[orange_x[0], orange_y[0]]]), orange_n_reps, axis=0)
                orange_embedding_sub = np.concatenate((orange_embedding_sub, or_reps), axis=0)
                or_reps = np.repeat(np.array([[orange_x[1], orange_y[1]]]), orange_n_reps, axis=0)
                orange_embedding_sub = np.concatenate((orange_embedding_sub, or_reps), axis=0)

                orangeGam = pg.LinearGAM(n_splines=8, spline_order=3, lam=10).fit(orange_embedding_sub[:, 0],
                                                                                  orange_embedding_sub[:, 1])
                nx_spacing = 100
                orange_GAM_xval = np.linspace(orange_minx, orange_maxx, nx_spacing * 2)
                yg_orange = orangeGam.predict(X=orange_GAM_xval)

                ax.plot(orange_GAM_xval, yg_orange, color='dimgrey', linewidth=2, zorder=3, linestyle=(0, (5, 2, 1, 2)),
                        dash_capstyle='round')

                cur_x1 = orange_GAM_xval[-1]
                cur_y1 = yg_orange[-1]
                cur_x2 = orange_GAM_xval[0]
                cur_y2 = yg_orange[0]
                if path_i >= 1:
                    for mmddi in range(2):
                        xy11 = euclidean_distances(np.array([cur_x1, cur_y1]).reshape(1, -1),
                                                   np.array([prev_x1, prev_y1]).reshape(1, -1))
                        xy12 = euclidean_distances(np.array([cur_x1, cur_y1]).reshape(1, -1),
                                                   np.array([prev_x2, prev_y2]).reshape(1, -1))
                        xy21 = euclidean_distances(np.array([cur_x2, cur_y2]).reshape(1, -1),
                                                   np.array([prev_x1, prev_y1]).reshape(1, -1))
                        xy22 = euclidean_distances(np.array([cur_x2, cur_y2]).reshape(1, -1),
                                                   np.array([prev_x2, prev_y2]).reshape(1, -1))
                        mmdd_temp_array = np.asarray([xy11, xy12, xy21, xy22])
                        mmdd_loc = np.where(mmdd_temp_array == np.min(mmdd_temp_array))[0][0]
                        if mmdd_loc == 0:
                            ax.plot([cur_x1, prev_x1], [cur_y1, prev_y1], color='black', linestyle=(0, (5, 2, 1, 2)),
                                    dash_capstyle='round')
                        if mmdd_loc == 1:
                            ax.plot([cur_x1, prev_x2], [cur_y1, prev_y2], color='black', linestyle=(0, (5, 2, 1, 2)),
                                    dash_capstyle='round')
                        if mmdd_loc == 2:
                            ax.plot([cur_x2, prev_x1], [cur_y2, prev_y1], color='black', linestyle=(0, (5, 2, 1, 2)),
                                    dash_capstyle='round')
                        if mmdd_loc == 3:
                            ax.plot([cur_x2, prev_x2], [cur_y2, prev_y2], color='black', linestyle=(0, (5, 2, 1, 2)),
                                    dash_capstyle='round')
                    if (path_x_start > path_x_end): direction_arrow_orange = -1  # going LEFT
                    if (path_x_start <= path_x_end): direction_arrow_orange = 1  # going RIGHT

                    if (abs(
                            path_x_start - path_x_end) > 2.5):  # |(abs(orange_m[path_i, 2] - orange_m[path_i + 1, 1]) > 1)):
                        if (direction_arrow_orange == -1):  # & :
                            ax.arrow(orange_GAM_xval[nx_spacing], yg_orange[nx_spacing],
                                     orange_GAM_xval[nx_spacing - 1] - orange_GAM_xval[nx_spacing],
                                     yg_orange[nx_spacing - 1] - yg_orange[nx_spacing], shape='full', lw=0,
                                     length_includes_head=True,
                                     head_width=0.5, color='dimgray', zorder=3)
                        if (direction_arrow_orange == 1):  # &(abs(orange_m[path_i,0]-orange_m[path_i+1,0])>0.5):
                            ax.arrow(orange_GAM_xval[nx_spacing], yg_orange[nx_spacing],
                                     orange_GAM_xval[nx_spacing + 1] - orange_GAM_xval[nx_spacing],
                                     yg_orange[nx_spacing + 1] - yg_orange[nx_spacing], shape='full', lw=0,
                                     length_includes_head=True,
                                     head_width=0.5,
                                     color='dimgray', zorder=3)
                prev_x1 = cur_x1
                prev_y1 = cur_y1
                prev_x2 = cur_x2
                prev_y2 = cur_y2

        ax.scatter(x_sc, y_sc, color='pink', zorder=3, label=str(ti), s=22)
        ax.text(x_sc + 0.5, y_sc + 0.5, 'TS ' + str(ti), color='black')

    return


def get_biased_weights(edgelist, weights, pt, round_no=1):
    # print('weights', type(weights), weights)
    # small nu means less biasing (0.5 is quite mild)
    # larger nu (in our case 1/nu) means more aggressive biasing https://en.wikipedia.org/wiki/Generalised_logistic_function
    print(len(edgelist), len(weights))
    bias_weight = []
    if round_no == 1:
        b = 1  # 1  # 0.5
    else:
        b = 20  # 20 twenty is used for all the CD34 Human cells
    K = 1
    c = 0
    C = 1
    nu = 1
    high_weights_th = np.mean(weights)
    high_pt_th = np.percentile(np.asarray(pt), 80)
    loc_high_weights = np.where(weights > high_weights_th)[0]
    loc_high_pt = np.where(np.asarray(pt) > high_pt_th)[0]
    # print('weight  hi th', high_weights_th)
    # print('loc hi pt', loc_high_pt)
    # print('loc hi weight', loc_high_weights)
    # print('edges of high weight', [edgelist[i] for i in loc_high_weights])
    edgelist_hi = [edgelist[i] for i in loc_high_weights]

    for i in loc_high_weights:
        # print('loc of high weight along edgeweight', i)
        start = edgelist[i][0]
        end = edgelist[i][1]
        # print('start and end node', start, end)
        if (start in loc_high_pt) | (end in loc_high_pt):
            # print("found a high pt high weight node", (start, end), pt[start], pt[end])
            weights[i] = 0.5 * np.mean(weights)

    upper_lim = np.percentile(weights, 90)  # 80
    lower_lim = np.percentile(weights, 10)  # 20
    weights = [i if i <= upper_lim else upper_lim for i in weights]
    weights = [i if i >= lower_lim else lower_lim for i in weights]
    for i, (start, end) in enumerate(edgelist):
        # print('i, start, end', i, start, end)
        Pt_a = pt[start]
        Pt_b = pt[end]
        P_ab = weights[i]
        t_ab = Pt_a - Pt_b

        Bias_ab = K / ((C + math.exp(b * (t_ab + c)))) ** nu
        new_weight = (Bias_ab * P_ab)
        bias_weight.append(new_weight)
        # print('tab', t_ab, 'pab', P_ab, 'biased_pab', new_weight)
    print('original weights', len(weights), list(enumerate(zip(edgelist, weights))))
    print('bias weights', list(enumerate(zip(edgelist, bias_weight))))
    # print('length bias weights', len(bias_weight))
    # bias_weight=np.asarray(bias_weight)
    # bias_weight = (bias_weight-np.min(bias_weight)+0.1)/(np.max(bias_weight)-np.min(bias_weight)+0.1)
    return list(bias_weight)


def expected_num_steps(start_i, N):
    n_t = N.shape[0]
    N_steps = np.dot(N, np.ones(n_t))
    n_steps_i = N_steps[start_i]
    return n_steps_i


def absorption_probability(N, R, absorption_state_j):
    M = np.dot(N, R)
    vec_prob_end_in_j = M[:, absorption_state_j]
    return M, vec_prob_end_in_j


def most_likely_path(P_transition_absorbing_markov, start_i, end_i):
    graph_absorbing_markov = 0  # ig() log weight them
    shortest_path = graph_absorbing_markov.shortest_path(start_i, end_i)
    print('the shortest path beginning at ', start_i, 'and ending in ', end_i, 'is:')
    return shortest_path


def draw_trajectory_gams(X_dimred, sc_supercluster_nn, cluster_labels, super_cluster_labels, super_edgelist, x_lazy,
                         alpha_teleport,
                         projected_sc_pt, true_label, knn, ncomp, final_super_terminal, sub_terminal_clusters,
                         title_str="hitting times", ):
    x = X_dimred[:, 0]
    y = X_dimred[:, 1]

    df = pd.DataFrame({'x': x, 'y': y, 'cluster': cluster_labels, 'super_cluster': super_cluster_labels,
                       'projected_sc_pt': projected_sc_pt},
                      columns=['x', 'y', 'cluster', 'super_cluster', 'projected_sc_pt'])
    df_mean = df.groupby('cluster', as_index=False).mean()
    sub_cluster_isin_supercluster = df_mean[['cluster', 'super_cluster']]

    print('sub_cluster_isin_supercluster', sub_cluster_isin_supercluster)
    sub_cluster_isin_supercluster = sub_cluster_isin_supercluster.sort_values(by='cluster')
    sub_cluster_isin_supercluster['int_supercluster'] = sub_cluster_isin_supercluster['super_cluster'].round(0).astype(
        int)
    print('sub_cluster_isin_supercluster', sub_cluster_isin_supercluster)

    print('final_super_terminal', final_super_terminal)
    df_super_mean = df.groupby('super_cluster', as_index=False).mean()

    pt = df_super_mean['projected_sc_pt'].values
    pt_int = [int(i) for i in pt]
    pt_str = [str(i) for i in pt_int]
    pt_sub = [str(int(i)) for i in df_mean['projected_sc_pt'].values]

    f, (ax1, ax2) = plt.subplots(1, 2, sharey=True)
    num_parc_group = len(set(true_label))
    line = np.linspace(0, 1, num_parc_group)
    for color, group in zip(line, sorted(set(true_label))):
        where = np.where(np.array(true_label) == group)[0]
        ax1.scatter(X_dimred[where, 0], X_dimred[where, 1], label=group, c=np.asarray(plt.cm.jet(color)).reshape(-1, 4),
                    alpha=0.5, s=4)
    ax1.legend(fontsize=6)
    ax1.set_title('true labels, ncomps:' + str(ncomp) + '. knn:' + str(knn))
    for e_i, (start, end) in enumerate(super_edgelist):
        print('start and end', start, end)

        if pt[start] >= pt[end]:
            temp = end
            end = start
            start = temp

        x_i_start = df[df['super_cluster'] == start]['x'].values  # groupby('cluster').mean()['x'].values
        y_i_start = df[df['super_cluster'] == start]['y'].values  # .groupby('cluster').mean()['y'].values
        x_i_end = df[df['super_cluster'] == end]['x'].values  # .groupby('cluster').mean()['x'].values
        y_i_end = df[df['super_cluster'] == end]['y'].values  # groupby('cluster').mean()['y'].values
        direction_arrow = 1

        super_start_x = X_dimred[sc_supercluster_nn[start], 0]  # df[df['super_cluster'] == start].mean()['x']
        super_end_x = X_dimred[sc_supercluster_nn[end], 0]  # df[df['super_cluster'] == end].mean()['x']
        super_start_y = X_dimred[sc_supercluster_nn[start], 1]  # df[df['super_cluster'] == start].mean()['y']
        super_end_y = X_dimred[sc_supercluster_nn[end], 1]  # df[df['super_cluster'] == end].mean()['y']
        print('super_start_x', start, super_start_x, super_start_y)
        if super_start_x > super_end_x: direction_arrow = -1
        ext_maxx = False
        minx = min(super_start_x, super_end_x)
        maxx = max(super_start_x, super_end_x)

        miny = min(super_start_y, super_end_y)
        maxy = max(super_start_y, super_end_y)

        x_val = np.concatenate([x_i_start, x_i_end])
        y_val = np.concatenate([y_i_start, y_i_end])

        idx_keep = np.where((x_val <= maxx) & (x_val >= minx))[
            0]  # np.where((X_dimred[:,0]<=maxx) & (X_dimred[:,0]>=minx))#
        idy_keep = np.where((y_val <= maxy) & (y_val >= miny))[
            0]  # np.where((X_dimred[:,1]<=maxy) & (X_dimred[:,1]>=miny))#

        idx_keep = np.intersect1d(idy_keep, idx_keep)

        x_val = x_val[idx_keep]  # X_dimred[idx_keep,0]#
        y_val = y_val[idx_keep]  # X_dimred[idx_keep,1]# y_val[idx_keep]
        print('start and end', start, '', end)

        super_mid_x = (super_start_x + super_end_x) / 2
        super_mid_y = (super_start_y + super_end_y) / 2
        from scipy.spatial import distance

        very_straight = False
        if abs(minx - maxx) <= 1:
            very_straight = True
            straight_level = 10
            noise = 0.01
            x_super = np.array(
                [super_start_x, super_end_x, super_start_x, super_end_x, super_start_x + noise, super_end_x + noise,
                 super_start_x - noise, super_end_x - noise, super_mid_x])
            y_super = np.array(
                [super_start_y, super_end_y, super_start_y, super_end_y, super_start_y + noise, super_end_y + noise,
                 super_start_y - noise, super_end_y - noise, super_mid_y])
        else:
            straight_level = 3
            noise = 0.1  # 0.05
            x_super = np.array(
                [super_start_x, super_end_x, super_start_x, super_end_x, super_start_x + noise, super_end_x + noise,
                 super_start_x - noise, super_end_x - noise])
            y_super = np.array(
                [super_start_y, super_end_y, super_start_y, super_end_y, super_start_y + noise, super_end_y + noise,
                 super_start_y - noise, super_end_y - noise])

        for i in range(straight_level):  # DO THE SAME FOR A MIDPOINT TOO
            y_super = np.concatenate([y_super, y_super])
            x_super = np.concatenate([x_super, x_super])

        list_selected_clus = list(zip(x_val, y_val))

        if (len(list_selected_clus) >= 1) & (very_straight == True):

            dist = distance.cdist([(super_mid_x, super_mid_y)], list_selected_clus, 'euclidean')

            if len(list_selected_clus) >= 2:
                k = 2
            else:
                k = 1
            midpoint_loc = dist[0].argsort()[:k]  # np.where(dist[0]==np.min(dist[0]))[0][0]

            midpoint_xy = []
            for i in range(k):
                midpoint_xy.append(list_selected_clus[midpoint_loc[i]])

            noise = 0.05

            if k == 1:
                mid_x = np.array([midpoint_xy[0][0], midpoint_xy[0][0] + noise, midpoint_xy[0][
                    0] - noise])  # ,midpoint_xy[1][0], midpoint_xy[1][0] + noise, midpoint_xy[1][0] - noise])
                mid_y = np.array([midpoint_xy[0][1], midpoint_xy[0][1] + noise, midpoint_xy[0][
                    1] - noise])  # ,midpoint_xy[1][1], midpoint_xy[1][1] + noise, midpoint_xy[1][1] - noise])
            if k == 2:
                mid_x = np.array(
                    [midpoint_xy[0][0], midpoint_xy[0][0] + noise, midpoint_xy[0][0] - noise, midpoint_xy[1][0],
                     midpoint_xy[1][0] + noise, midpoint_xy[1][0] - noise])
                mid_y = np.array(
                    [midpoint_xy[0][1], midpoint_xy[0][1] + noise, midpoint_xy[0][1] - noise, midpoint_xy[1][1],
                     midpoint_xy[1][1] + noise, midpoint_xy[1][1] - noise])
            for i in range(3):
                mid_x = np.concatenate([mid_x, mid_x])
                mid_y = np.concatenate([mid_y, mid_y])

            x_super = np.concatenate([x_super, mid_x])
            y_super = np.concatenate([y_super, mid_y])
        x_val = np.concatenate([x_val, x_super])
        y_val = np.concatenate([y_val, y_super])

        x_val = x_val.reshape((len(x_val), -1))
        y_val = y_val.reshape((len(y_val), -1))
        xp = np.linspace(minx, maxx, 500)

        gam50 = pg.LinearGAM(n_splines=4, spline_order=3, lam=10).gridsearch(x_val, y_val)

        XX = gam50.generate_X_grid(term=0, n=500)

        preds = gam50.predict(XX)

        if ext_maxx == False:
            idx_keep = np.where((xp <= (maxx)) & (xp >= (minx)))[0]  # minx+3
        else:
            idx_keep = np.where((xp <= (maxx)) & (xp >= (minx)))[0]  # maxx-3

        # cc = ['black', 'red', 'blue', 'yellow', 'pink'][random.randint(0, 4)]
        ax2.plot(XX, preds, linewidth=2, c='dimgray')  # 1

        # med_loc = np.where(xp == np.median(xp[idx_keep]))[0]
        mean_temp = np.mean(xp[idx_keep])
        closest_val = xp[idx_keep][0]
        closest_loc = idx_keep[0]

        for i, xp_val in enumerate(xp[idx_keep]):

            if abs(xp_val - mean_temp) < abs(closest_val - mean_temp):
                closest_val = xp_val
                closest_loc = idx_keep[i]
        step = 1
        if direction_arrow == 1:
            print('arrow direction', direction_arrow)
            ax2.arrow(xp[closest_loc], preds[closest_loc], xp[closest_loc + step] - xp[closest_loc],
                      preds[closest_loc + step] - preds[closest_loc], shape='full', lw=0, length_includes_head=True,
                      head_width=1, color='dimgray')  # , head_starts_at_zero = direction_arrow )

        else:
            ax2.arrow(xp[closest_loc], preds[closest_loc], xp[closest_loc - step] - xp[closest_loc],
                      preds[closest_loc - step] - preds[closest_loc], shape='full', lw=0, length_includes_head=True,
                      head_width=1, color='dimgray')

    x_cluster = df_mean['x']
    y_cluster = df_mean['y']

    num_parc_group = len(set(cluster_labels))

    c_edge = []
    width_edge = []
    pen_color = []
    super_cluster_label = []
    terminal_count_ = 0
    dot_size = []
    for i in range(len(set(super_cluster_labels))):
        if i in final_super_terminal:
            print('super cluster', i, 'is a super terminal with sub_terminal cluster',
                  sub_terminal_clusters[terminal_count_])
            width_edge.append(2)
            c_edge.append('yellow')  # ('yellow')
            pen_color.append('black')
            super_cluster_label.append('TS' + str(sub_terminal_clusters[terminal_count_]))  # +'('+str(i)+')')
            dot_size.append(60)
            terminal_count_ = terminal_count_ + 1
        else:
            width_edge.append(0)
            c_edge.append('black')
            pen_color.append('red')
            # super_cluster_label.append(str(i))
            super_cluster_label.append('')
            dot_size.append(0)  # 40

    # ax2.scatter(x_cluster, y_cluster, c='red') #doesnt visualize as well to just take the embedding cluster-mean x,y values

    # text annotations for the super cluster locations
    # for i, type in enumerate(pt_str):
    # ax2.text(df_super_mean['x'][i], df_super_mean['y'][i], 'C' + str(i), weight='bold')

    # for i in range(len(x_cluster)):
    # ax2.text(x_cluster[i], y_cluster[i], 'c' + str(i))
    ax2.set_title('lazy:' + str(x_lazy) + ' teleport' + str(alpha_teleport) + 'super_knn:' + str(knn))
    # ax2.set_title('super_knn:' + str(knn) )
    ax2.scatter(X_dimred[:, 0], X_dimred[:, 1], c=projected_sc_pt, cmap='viridis_r', alpha=0.5, s=6)
    # ax2.scatter(df_super_mean['x'], df_super_mean['y'], c='black', s=60, edgecolors = c_edge, linewidth = width_edge)
    count_ = 0
    sc_supercluster_nn = [sc_supercluster_nn[scs] for scs in sc_supercluster_nn]
    for i, c, w, pc, dsz in zip(sc_supercluster_nn, c_edge, width_edge, pen_color, dot_size):
        ax2.scatter(X_dimred[i, 0], X_dimred[i, 1], c='black', s=dsz, edgecolors=c, linewidth=w)
        ax2.text(X_dimred[i, 0] + 0.5, X_dimred[i, 1] + 0.5, super_cluster_label[count_],
                 color=pc)  # using the SC_NN location is good
        count_ = count_ + 1

    plt.title(title_str)

    return


def draw_trajectory_dimred(X_dimred, sc_supercluster_nn, cluster_labels, super_cluster_labels, super_edgelist, x_lazy,
                           alpha_teleport,
                           projected_sc_pt, true_label, knn, ncomp, final_super_terminal,
                           title_str="hitting times", ):
    x = X_dimred[:, 0]
    y = X_dimred[:, 1]

    df = pd.DataFrame({'x': x, 'y': y, 'cluster': cluster_labels, 'super_cluster': super_cluster_labels,
                       'projected_sc_pt': projected_sc_pt},
                      columns=['x', 'y', 'cluster', 'super_cluster', 'projected_sc_pt'])
    df_mean = df.groupby('cluster', as_index=False).mean()
    sub_cluster_isin_supercluster = df_mean[['cluster', 'super_cluster']]

    sub_cluster_isin_supercluster = sub_cluster_isin_supercluster.sort_values(by='cluster')
    sub_cluster_isin_supercluster['int_supercluster'] = sub_cluster_isin_supercluster['super_cluster'].round(1).astype(
        int)

    df_super_mean = df.groupby('super_cluster', as_index=False).mean()

    pt = df_super_mean['projected_sc_pt'].values
    pt_int = [int(i) for i in pt]
    pt_str = [str(i) for i in pt_int]
    pt_sub = [str(int(i)) for i in df_mean['projected_sc_pt'].values]

    f, (ax1, ax2) = plt.subplots(1, 2, sharey=True)
    num_parc_group = len(set(true_label))
    line = np.linspace(0, 1, num_parc_group)
    for color, group in zip(line, set(true_label)):
        where = np.where(np.array(true_label) == group)[0]
        ax1.scatter(X_dimred[where, 0], X_dimred[where, 1], label=group, c=np.asarray(plt.cm.jet(color)).reshape(-1, 4))
    ax1.legend(fontsize=6)
    ax1.set_title('true labels, ncomps:' + str(ncomp) + '. knn:' + str(knn))
    for e_i, (start, end) in enumerate(super_edgelist):

        if pt[start] >= pt[end]:
            temp = end
            end = start
            start = temp

        x_i_start = df[df['super_cluster'] == start].groupby('cluster').mean()['x'].values
        y_i_start = df[df['super_cluster'] == start].groupby('cluster').mean()['y'].values
        x_i_end = df[df['super_cluster'] == end].groupby('cluster').mean()['x'].values
        y_i_end = df[df['super_cluster'] == end].groupby('cluster').mean()['y'].values
        direction_arrow = 1

        super_start_x = X_dimred[sc_supercluster_nn[start], 0]  # df[df['super_cluster'] == start].mean()['x']
        super_end_x = X_dimred[sc_supercluster_nn[end], 0]  # df[df['super_cluster'] == end].mean()['x']
        super_start_y = X_dimred[sc_supercluster_nn[start], 1]  # df[df['super_cluster'] == start].mean()['y']
        super_end_y = X_dimred[sc_supercluster_nn[end], 1]  # df[df['super_cluster'] == end].mean()['y']

        if super_start_x > super_end_x: direction_arrow = -1
        ext_maxx = False
        minx = min(super_start_x, super_end_x)
        maxx = max(super_start_x, super_end_x)

        miny = min(super_start_y, super_end_y)
        maxy = max(super_start_y, super_end_y)

        x_val = np.concatenate([x_i_start, x_i_end])
        y_val = np.concatenate([y_i_start, y_i_end])

        idx_keep = np.where((x_val <= maxx) & (x_val >= minx))[0]
        idy_keep = np.where((y_val <= maxy) & (y_val >= miny))[0]
        print('len x-val before intersect', len(x_val))
        idx_keep = np.intersect1d(idy_keep, idx_keep)
        x_val = x_val[idx_keep]
        y_val = y_val[idx_keep]

        super_mid_x = (super_start_x + super_end_x) / 2
        super_mid_y = (super_start_y + super_end_y) / 2
        from scipy.spatial import distance

        very_straight = False
        if abs(minx - maxx) <= 1:
            very_straight = True
            straight_level = 10
            noise = 0.01
            x_super = np.array(
                [super_start_x, super_end_x, super_start_x, super_end_x, super_start_x + noise, super_end_x + noise,
                 super_start_x - noise, super_end_x - noise, super_mid_x])
            y_super = np.array(
                [super_start_y, super_end_y, super_start_y, super_end_y, super_start_y + noise, super_end_y + noise,
                 super_start_y - noise, super_end_y - noise, super_mid_y])
        else:
            straight_level = 3
            noise = 0.1  # 0.05
            x_super = np.array(
                [super_start_x, super_end_x, super_start_x, super_end_x, super_start_x + noise, super_end_x + noise,
                 super_start_x - noise, super_end_x - noise])
            y_super = np.array(
                [super_start_y, super_end_y, super_start_y, super_end_y, super_start_y + noise, super_end_y + noise,
                 super_start_y - noise, super_end_y - noise])

        for i in range(straight_level):  # DO THE SAME FOR A MIDPOINT TOO
            y_super = np.concatenate([y_super, y_super])
            x_super = np.concatenate([x_super, x_super])

        list_selected_clus = list(zip(x_val, y_val))

        if (len(list_selected_clus) >= 1) & (very_straight == True):

            dist = distance.cdist([(super_mid_x, super_mid_y)], list_selected_clus, 'euclidean')
            print('dist', dist)
            if len(list_selected_clus) >= 2:
                k = 2
            else:
                k = 1
            midpoint_loc = dist[0].argsort()[:k]  # np.where(dist[0]==np.min(dist[0]))[0][0]
            print('midpoint loc', midpoint_loc)
            midpoint_xy = []
            for i in range(k):
                midpoint_xy.append(list_selected_clus[midpoint_loc[i]])

            # midpoint_xy = list_selected_clus[midpoint_loc]
            noise = 0.05
            print(midpoint_xy, 'is the midpoint between clus', pt[start], 'and ', pt[end])
            if k == 1:
                mid_x = np.array([midpoint_xy[0][0], midpoint_xy[0][0] + noise, midpoint_xy[0][
                    0] - noise])  # ,midpoint_xy[1][0], midpoint_xy[1][0] + noise, midpoint_xy[1][0] - noise])
                mid_y = np.array([midpoint_xy[0][1], midpoint_xy[0][1] + noise, midpoint_xy[0][
                    1] - noise])  # ,midpoint_xy[1][1], midpoint_xy[1][1] + noise, midpoint_xy[1][1] - noise])
            if k == 2:
                mid_x = np.array(
                    [midpoint_xy[0][0], midpoint_xy[0][0] + noise, midpoint_xy[0][0] - noise, midpoint_xy[1][0],
                     midpoint_xy[1][0] + noise, midpoint_xy[1][0] - noise])
                mid_y = np.array(
                    [midpoint_xy[0][1], midpoint_xy[0][1] + noise, midpoint_xy[0][1] - noise, midpoint_xy[1][1],
                     midpoint_xy[1][1] + noise, midpoint_xy[1][1] - noise])
            for i in range(3):
                mid_x = np.concatenate([mid_x, mid_x])
                mid_y = np.concatenate([mid_y, mid_y])

            x_super = np.concatenate([x_super, mid_x])
            y_super = np.concatenate([y_super, mid_y])
        x_val = np.concatenate([x_val, x_super])
        y_val = np.concatenate([y_val, y_super])

        z = np.polyfit(x_val, y_val, 2)

        xp = np.linspace(minx, maxx, 500)
        p = np.poly1d(z)

        smooth = p(xp)
        if ext_maxx == False:
            idx_keep = np.where((xp <= (maxx)) & (xp >= (minx)))[0]  # minx+3
        else:
            idx_keep = np.where((xp <= (maxx)) & (xp >= (minx)))[0]  # maxx-3
        ax2.plot(xp[idx_keep], smooth[idx_keep], linewidth=3, c='dimgrey')

        # med_loc = np.where(xp == np.median(xp[idx_keep]))[0]
        mean_temp = np.mean(xp[idx_keep])
        closest_val = xp[idx_keep][0]
        closest_loc = idx_keep[0]

        for i, xp_val in enumerate(xp[idx_keep]):

            if abs(xp_val - mean_temp) < abs(closest_val - mean_temp):
                closest_val = xp_val
                closest_loc = idx_keep[i]
        step = 1
        if direction_arrow == 1:  # smooth instead of preds
            ax2.arrow(xp[closest_loc], smooth[closest_loc], xp[closest_loc + step] - xp[closest_loc],
                      smooth[closest_loc + step] - smooth[closest_loc], shape='full', lw=0, length_includes_head=True,
                      head_width=1, color='dimgrey')  # , head_starts_at_zero = direction_arrow )

        else:
            ax2.arrow(xp[closest_loc], smooth[closest_loc], xp[closest_loc - step] - xp[closest_loc],
                      smooth[closest_loc - step] - smooth[closest_loc], shape='full', lw=0, length_includes_head=True,
                      head_width=1, color='dimgrey')

    x_cluster = df_mean['x']
    y_cluster = df_mean['y']

    num_parc_group = len(set(cluster_labels))

    c_edge = []
    width_edge = []
    for i in range(num_parc_group):
        if i in final_super_terminal:
            width_edge.append(2.5)
            c_edge.append('yellow')
        else:
            width_edge.append(0)
            c_edge.append('black')

    ax2.scatter(x_cluster, y_cluster, c='red')

    for i, type in enumerate(pt_str):
        ax2.text(df_super_mean['x'][i], df_super_mean['y'][i], 'C' + str(i), weight='bold')

    for i in range(len(x_cluster)):
        ax2.text(x_cluster[i], y_cluster[i], pt_sub[i] + 'c' + str(i))
    ax2.set_title('lazy:' + str(x_lazy) + ' teleport' + str(alpha_teleport) + 'super_knn:' + str(knn))

    ax2.scatter(X_dimred[:, 0], X_dimred[:, 1], c=projected_sc_pt, cmap='viridis_r', alpha=0.5)
    ax2.scatter(df_super_mean['x'], df_super_mean['y'], c='black', s=60, edgecolors=c_edge, linewidth=width_edge)
    plt.title(title_str)
    return


def csr_mst(adjacency_matrix):
    # return minimum spanning tree from adjacency matrix (csr)
    Tcsr = adjacency_matrix.copy()
    n_components_mst, comp_labels_mst = connected_components(csgraph=Tcsr, directed=False, return_labels=True)
    print('number of components before mst', n_components_mst)
    print('len Tcsr data', len(Tcsr.data))
    Tcsr.data = -1 * Tcsr.data
    Tcsr.data = Tcsr.data - np.min(Tcsr.data)
    Tcsr.data = Tcsr.data + 1
    print('len Tcsr data', len(Tcsr.data))
    Tcsr = minimum_spanning_tree(Tcsr)  # adjacency_matrix)
    n_components_mst, comp_labels_mst = connected_components(csgraph=Tcsr, directed=False, return_labels=True)
    print('number of components after mst', n_components_mst)
    Tcsr = (Tcsr + Tcsr.T) * 0.5  # make symmetric
    print('number of components after symmetric mst', n_components_mst)
    print('len Tcsr data', len(Tcsr.data))
    return Tcsr


def connect_all_components(MSTcsr, cluster_graph_csr, adjacency_matrix):
    # connect forest of MSTs (csr)

    n_components, comp_labels = connected_components(csgraph=cluster_graph_csr, directed=False, return_labels=True)
    while n_components > 1:
        sub_td = MSTcsr[comp_labels == 0, :][:, comp_labels != 0]
        print('minimum value of link connecting components', np.min(sub_td.data))
        locxy = scipy.sparse.find(MSTcsr == np.min(sub_td.data))
        for i in range(len(locxy[0])):
            if (comp_labels[locxy[0][i]] == 0) & (comp_labels[locxy[1][i]] != 0):
                x = locxy[0][i]
                y = locxy[1][i]
        minval = adjacency_matrix[x, y]
        cluster_graph_csr[x, y] = minval
        n_components, comp_labels = connected_components(csgraph=cluster_graph_csr, directed=False, return_labels=True)
        print('number of connected componnents after reconnecting ', n_components)
    return cluster_graph_csr


def local_pruning_clustergraph_mst(adjacency_matrix, global_pruning_std=1, max_outgoing=30, preserve_disconnected=True):
    # larger pruning_std factor means less pruning
    # the mst is only used to reconnect components that become disconnect due to pruning
    from scipy.sparse.csgraph import minimum_spanning_tree

    Tcsr = csr_mst(adjacency_matrix)

    initial_links_n = len(adjacency_matrix.data)

    n_components_0, comp_labels_0 = connected_components(csgraph=adjacency_matrix, directed=False, return_labels=True)
    print('number of components before pruning', n_components_0, comp_labels_0)
    adjacency_matrix = scipy.sparse.csr_matrix.todense(adjacency_matrix)
    row_list = []
    col_list = []
    weight_list = []
    neighbor_array = adjacency_matrix  # not listed in in any order of proximity

    n_cells = neighbor_array.shape[0]
    rowi = 0

    for i in range(neighbor_array.shape[0]):
        row = np.asarray(neighbor_array[i, :]).flatten()
        # print('row, row')
        n_nonz = np.sum(row > 0)
        # print('n nonzero 1', n_nonz)
        n_nonz = min(n_nonz, max_outgoing)

        to_keep_index = np.argsort(row)[::-1][0:n_nonz]  # np.where(row>np.mean(row))[0]#
        # print('to keep', to_keep_index)
        updated_nn_weights = list(row[to_keep_index])
        for ik in range(len(to_keep_index)):
            row_list.append(rowi)
            col_list.append(to_keep_index[ik])
            dist = updated_nn_weights[ik]
            weight_list.append(dist)
        rowi = rowi + 1
    final_links_n = len(weight_list)
    print('final links n', final_links_n)
    cluster_graph_csr = csr_matrix((np.array(weight_list), (np.array(row_list), np.array(col_list))),
                                   shape=(n_cells, n_cells))

    sources, targets = cluster_graph_csr.nonzero()
    mask = np.zeros(len(sources), dtype=bool)

    cluster_graph_csr.data = cluster_graph_csr.data / (np.std(cluster_graph_csr.data))  # normalize
    threshold_global = np.mean(cluster_graph_csr.data) - global_pruning_std * np.std(cluster_graph_csr.data)
    mask |= (cluster_graph_csr.data < (threshold_global))  # smaller Jaccard weight means weaker edge

    cluster_graph_csr.data[mask] = 0
    cluster_graph_csr.eliminate_zeros()
    print('shape of cluster graph', cluster_graph_csr.shape)

    n_components, comp_labels = connected_components(csgraph=cluster_graph_csr, directed=False, return_labels=True)
    print('number of connected components after pruning', n_components)
    if (preserve_disconnected == True) & (n_components > n_components_0):  # preserve initial disconnected components
        Td = Tcsr.todense()
        Td[Td == 0] = 999.999
        n_components_ = n_components
        while n_components_ > n_components_0:
            for i in range(n_components_0):
                loc_x = np.where(comp_labels_0 == i)[0]

                len_i = len(set(comp_labels[loc_x]))
                print('locx', loc_x, len_i)

                while len_i > 1:
                    s = list(set(comp_labels[loc_x]))
                    loc_notxx = np.intersect1d(loc_x, np.where((comp_labels != s[0]))[0])
                    # print('loc_notx', loc_notxx)
                    loc_xx = np.intersect1d(loc_x, np.where((comp_labels == s[0]))[0])
                    sub_td = Td[loc_xx, :][:, loc_notxx]
                    # print('subtd-min', np.min(sub_td))

                    locxy = np.where(Td == np.min(sub_td))

                    for i in range(len(locxy[0])):
                        if (comp_labels[locxy[0][i]] != comp_labels[locxy[1][i]]):
                            x = locxy[0][i]
                            y = locxy[1][i]
                    minval = adjacency_matrix[x, y]
                    print('inside reconnecting components while preserving original ', x, y, minval)
                    cluster_graph_csr[x, y] = minval
                    n_components_, comp_labels = connected_components(csgraph=cluster_graph_csr, directed=False,
                                                                      return_labels=True)
                    loc_x = np.where(comp_labels_0 == i)[0]
                    len_i = len(set(comp_labels[loc_x]))
                print('number of connected componnents after reconnecting ', n_components_)
    '''                
    if (n_components > 1) & (preserve_disconnected == False):

        cluster_graph_csr = connect_all_components(Tcsr, cluster_graph_csr, adjacency_matrix)
        n_components, comp_labels = connected_components(csgraph=cluster_graph_csr, directed=False, return_labels=True)
    '''
    sources, targets = cluster_graph_csr.nonzero()
    edgelist = list(zip(sources, targets))

    edgeweights = cluster_graph_csr.data / (np.std(cluster_graph_csr.data))

    trimmed_n = (initial_links_n - final_links_n) * 100 / initial_links_n
    trimmed_n_glob = (initial_links_n - len(edgeweights)) / initial_links_n
    if global_pruning_std < 0.5:
        print("percentage links trimmed from local pruning relative to start", trimmed_n)
        print("percentage links trimmed from global pruning relative to start", trimmed_n_glob)
    return edgeweights, edgelist, comp_labels


def get_sparse_from_igraph(graph, weight_attr=None):
    edges = graph.get_edgelist()
    if weight_attr is None:
        weights = [1] * len(edges)
    else:
        weights = graph.es[weight_attr]
    if not graph.is_directed():
        edges.extend([(v, u) for u, v in edges])
        weights.extend(weights)
    shape = graph.vcount()
    shape = (shape, shape)
    if len(edges) > 0:
        return csr_matrix((weights, zip(*edges)), shape=shape)
    else:
        return csr_matrix(shape)


class PARC:
    def __init__(self, data, true_label=None, anndata=None, dist_std_local=2, jac_std_global='median',
                 keep_all_local_dist='auto',
                 too_big_factor=0.4, small_pop=10, jac_weighted_edges=True, knn=30, n_iter_leiden=5, random_seed=42,
                 num_threads=-1, distance='l2', time_smallpop=15, pseudotime=False,
                 path='/home/shobi/Trajectory/', super_cluster_labels=False,
                 super_node_degree_list=False, super_terminal_cells=False, x_lazy=0.95, alpha_teleport=0.99,
                 root_user="root_cluster", preserve_disconnected=True, dataset="humanCD34", super_terminal_clusters=[],
                 do_magic_bool=False, is_coarse=True, csr_full_graph='', ig_full_graph='', csr_array_pruned='',
                 full_neighbor_array=''):
        # higher dist_std_local means more edges are kept
        # highter jac_std_global means more edges are kept
        if keep_all_local_dist == 'auto':
            if data.shape[0] > 100000:
                keep_all_local_dist = True  # skips local pruning to increase speed
            else:
                keep_all_local_dist = False

        self.data = data
        self.true_label = true_label
        self.anndata = anndata
        self.dist_std_local = dist_std_local
        self.jac_std_global = jac_std_global  ##0.15 is also a recommended value performing empirically similar to 'median'
        self.keep_all_local_dist = keep_all_local_dist
        self.too_big_factor = too_big_factor  ##if a cluster exceeds this share of the entire cell population, then the PARC will be run on the large cluster. at 0.4 it does not come into play
        self.small_pop = small_pop  # smallest cluster population to be considered a community
        self.jac_weighted_edges = jac_weighted_edges
        self.knn = knn
        self.n_iter_leiden = n_iter_leiden
        self.random_seed = random_seed  # enable reproducible Leiden clustering
        self.num_threads = num_threads  # number of threads used in KNN search/construction
        self.distance = distance  # Euclidean distance 'l2' by default; other options 'ip' and 'cosine'
        self.time_smallpop = time_smallpop
        self.pseudotime = pseudotime

        self.path = path

        self.super_cluster_labels = super_cluster_labels
        self.super_node_degree_list = super_node_degree_list
        self.super_terminal_cells = super_terminal_cells
        self.x_lazy = x_lazy  # 1-x = probability of staying in same node
        self.alpha_teleport = alpha_teleport  # 1-alpha is probability of jumping
        self.root_user = root_user
        self.preserve_disconnected = preserve_disconnected
        self.dataset = dataset
        self.super_terminal_clusters = super_terminal_clusters
        self.do_magic_bool = do_magic_bool
        self.is_coarse = is_coarse
        self.csr_full_graph = csr_full_graph
        self.ig_full_graph = ig_full_graph
        self.csr_array_pruned = csr_array_pruned
        self.full_neighbor_array = full_neighbor_array

    def knngraph_visual(self, data_visual, knn_umap=15, downsampled=False):
        k_umap = knn_umap
        t0 = time.time()
        # neighbors in array are not listed in in any order of proximity
        if downsampled == False:
            self.knn_struct.set_ef(k_umap + 1)
            neighbor_array, distance_array = self.knn_struct.knn_query(self.data, k=k_umap)
        else:
            knn_struct_umap = self.make_knn_struct(visual=True, data_visual=data_visual)
            knn_struct_umap.set_ef(k_umap + 1)
            neighbor_array, distance_array = knn_struct_umap.knn_query(data_visual, k=k_umap)
        row_list = []
        n_neighbors = neighbor_array.shape[1]
        n_cells = neighbor_array.shape[0]
        print('ncells and neighs', n_cells, n_neighbors)

        dummy = np.transpose(np.ones((n_neighbors, n_cells)) * range(0, n_cells)).flatten()
        print('dummy size', dummy.size)
        row_list.extend(list(np.transpose(np.ones((n_neighbors, n_cells)) * range(0, n_cells)).flatten()))

        row_min = np.min(distance_array, axis=1)
        row_sigma = np.std(distance_array, axis=1)

        distance_array = (distance_array - row_min[:, np.newaxis]) / row_sigma[:, np.newaxis]

        col_list = neighbor_array.flatten().tolist()
        distance_array = distance_array.flatten()
        distance_array = np.sqrt(distance_array)
        distance_array = distance_array * -1

        weight_list = np.exp(distance_array)

        threshold = np.mean(weight_list) + 2 * np.std(weight_list)

        weight_list[weight_list >= threshold] = threshold

        weight_list = weight_list.tolist()
        print('weight list', len(weight_list))

        graph = csr_matrix((np.array(weight_list), (np.array(row_list), np.array(col_list))),
                           shape=(n_cells, n_cells))

        graph_transpose = graph.T
        prod_matrix = graph.multiply(graph_transpose)

        graph = graph_transpose + graph - prod_matrix
        return graph

    def run_umap_hnsw(self, X_input, graph, n_components=2, alpha: float = 1.0, negative_sample_rate: int = 5,
                      gamma: float = 1.0, spread=1.0, min_dist=0.1, init_pos='spectral', random_state=1, ):

        from umap.umap_ import find_ab_params, simplicial_set_embedding
        import matplotlib.pyplot as plt

        a, b = find_ab_params(spread, min_dist)
        print('a,b, spread, dist', a, b, spread, min_dist)
        t0 = time.time()
        X_umap = simplicial_set_embedding(data=X_input, graph=graph, n_components=n_components, initial_alpha=alpha,
                                          a=a, b=b, n_epochs=0, metric_kwds={}, gamma=gamma,
                                          negative_sample_rate=negative_sample_rate, init=init_pos,
                                          random_state=np.random.RandomState(random_state), metric='euclidean',
                                          verbose=1)
        return X_umap

    def get_terminal_clusters(self, A, markov_pt, root_ai):
        n_ = A.shape[0]

        if n_ <= 10: n_outlier_std = 3
        if (n_ <= 40) & (n_ > 10): n_outlier_std = 2  # 40

        if n_ >= 40: n_outlier_std = 1

        pop_list = []

        print('get terminal', set(self.labels), np.where(self.labels == 0))
        for i in list(set(self.labels)):
            pop_list.append(len(np.where(self.labels == i)[0]))
        # we weight the out-degree based on the population of clusters to avoid allowing small clusters to become the terminals based on population alone
        A_new = A.copy()
        for i in range(A.shape[0]):
            for j in range(A.shape[0]):
                A_new[i, j] = A[i, j] * (pop_list[i] + pop_list[j]) / (pop_list[i] * pop_list[j])

        # make an igraph graph to compute the closeness
        g_dis = ig.Graph.Adjacency(
            (A_new > 0).tolist())  # need to manually add the weights as igraph treates A>0 as boolean
        g_dis.es['weights'] = 1 / A_new[A_new.nonzero()]  # we want "distances" not weights for closeness and betweeness

        betweenness_score = g_dis.betweenness(weights='weights')
        betweenness_score_array = np.asarray(betweenness_score)
        betweenness_score_takeout_outlier = betweenness_score_array[betweenness_score_array < (
                    np.mean(betweenness_score_array) + n_outlier_std * np.std(betweenness_score_array))]
        betweenness_list = [i for i, score in enumerate(betweenness_score) if score < (
                    np.mean(betweenness_score_takeout_outlier) - 0 * np.std(betweenness_score_takeout_outlier))]

        closeness_score = g_dis.closeness(mode='ALL', cutoff=None, weights='weights', normalized=True)
        closeness_score_array = np.asarray(closeness_score)
        closeness_score_takeout_outlier = closeness_score_array[
            closeness_score_array < (np.mean(closeness_score_array) + n_outlier_std * np.std(closeness_score_array))]
        closeness_list = [i for i, score in enumerate(closeness_score) if
                          score < (np.mean(closeness_score_takeout_outlier) - 0 * np.std(
                              closeness_score_takeout_outlier))]
        print('closeness_score ', [(i, score) for i, score in enumerate(closeness_score)])
        print('closeness_score shortlist', closeness_list)

        print('betweeness_score ', [(i, score) for i, score in enumerate(betweenness_score)])
        print('betweeness_score shortlist', betweenness_list)

        out_deg = A_new.sum(axis=1)
        in_deg = A_new.sum(axis=0)
        out_deg = np.asarray(out_deg)

        outdegree_score_takeout_outlier = out_deg[out_deg < (np.mean(out_deg) + n_outlier_std * np.std(out_deg))]
        outdeg_list = [i for i, score in enumerate(out_deg) if
                       score < (np.mean(outdegree_score_takeout_outlier) - 0 * np.std(outdegree_score_takeout_outlier))]

        markov_pt = np.asarray(markov_pt)
        markov_pt_takeout_outlier = markov_pt[markov_pt < (np.mean(markov_pt) + n_outlier_std * np.std(markov_pt))]

        print('number of clusters', n_)
        if n_ <= 10:
            loc_deg = np.where(out_deg <= np.percentile(out_deg, 50))[0]
            print('low deg super', loc_deg)
            loc_pt = np.where(markov_pt >= np.percentile(markov_pt, 60))[
                0]  # 60 Ttoy #10 for human but not sure ever in play
            loc_deg_in = np.where(in_deg <= np.percentile(in_deg, 10))[0]
            print('high pt super', loc_pt)
        if (n_ <= 40) & (n_ > 10):
            loc_deg = np.where(out_deg <= np.percentile(out_deg, 50))[
                0]  # np.mean(out_deg[out_deg>(np.mean(out_deg)-1*np.std(out_deg))]))[0]#np.percentile(out_deg, 50))[0]#np.mean(out_deg[out_deg>(np.mean(out_deg)-1*np.std(out_deg))]))[0]#np.percentile(out_deg, 50))[0]  # 30 for Toy #was 50 for Human
            loc_deg_in = np.where(in_deg <= np.percentile(in_deg, 20))[0]
            print('low deg super', loc_deg)
            print('low in-deg super', loc_deg_in)
            loc_pt = np.where(markov_pt >= np.percentile(markov_pt, 10))[0]  # 60 Toy #10 Human
            print('high pt super', loc_pt)
        if n_ > 40:
            loc_deg = np.where(out_deg <= np.percentile(out_deg, 50))[0]  # 15 Toy
            print('low deg', loc_deg)
            loc_pt = np.where(markov_pt >= np.percentile(markov_pt, 40))[0]  # 60Toy #30 Human
            print('high pt', loc_pt)
            loc_deg_in = np.where(in_deg <= np.percentile(in_deg, 10))[0]
        loc_deg = outdeg_list

        terminal_clusters_1 = list(set(closeness_list) & set(betweenness_list))
        terminal_clusters_2 = list(set(closeness_list) & set(loc_deg))
        terminal_clusters_3 = list(set(betweenness_list) & set(loc_deg))
        terminal_clusters = list(set(terminal_clusters_1) | set(terminal_clusters_2))
        terminal_clusters = list(set(terminal_clusters) | set(terminal_clusters_3))
        terminal_clusters = list(set(terminal_clusters) & set(loc_pt))

        terminal_org = terminal_clusters.copy()
        print('original terminal clusters', terminal_org)
        for terminal_i in terminal_org:
            if terminal_i in terminal_clusters:
                removed_terminal_i = False
            else:
                removed_terminal_i = True
            # print('terminal state', terminal_i)
            count_nn = 0
            ts_neigh = []
            neigh_terminal = np.where(A[:, terminal_i] > 0)[0]
            if neigh_terminal.size > 0:
                for item in neigh_terminal:
                    # print('terminal state', terminal_i)
                    if item in terminal_clusters:
                        ts_neigh.append(item)
                        print('item and terminal',
                              item, terminal_clusters)
                        count_nn = count_nn + 1

                    if n_ >= 10:
                        if item == root_ai:  # if the terminal state is a neighbor of
                            terminal_clusters.remove(terminal_i)
                            print('we removed cluster', terminal_i, 'from the shortlist of terminal states ')
                            removed_terminal_i = True
                if count_nn >= 3:
                    if removed_terminal_i == False:
                        temp_remove = terminal_i
                        temp_time = markov_pt[terminal_i]
                        for to_remove_i in ts_neigh:
                            if markov_pt[to_remove_i] < temp_time:
                                temp_remove = to_remove_i
                                temp_time = markov_pt[to_remove_i]
                        terminal_clusters.remove(temp_remove)
                    print('TS', terminal_i, 'had 3 or more neighboring terminal states', ts_neigh,
                          ' and so we removed,', temp_remove)

        print('terminal_clusters', terminal_clusters)
        return terminal_clusters

    def compute_hitting_time(self, sparse_graph, root, x_lazy, alpha_teleport, number_eig=0):
        # 1- alpha is the probabilty of teleporting
        # 1- x_lazy is the probability of staying in current state (be lazy)

        beta_teleport = 2 * (1 - alpha_teleport) / (2 - alpha_teleport)
        N = sparse_graph.shape[0]
        # print('adjacency in compute hitting', sparse_graph)
        # sparse_graph = scipy.sparse.csr_matrix(sparse_graph)
        print('start compute hitting')
        A = scipy.sparse.csr_matrix.todense(sparse_graph)  # A is the adjacency matrix
        print('is graph symmetric', (A.transpose() == A).all())
        lap = csgraph.laplacian(sparse_graph,
                                normed=False)  # compute regular laplacian (normed = False) to infer the degree matrix where D = L+A
        # see example and definition in the SciPy ref https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.laplacian.html
        A = scipy.sparse.csr_matrix.todense(lap)
        print('is laplacian symmetric', (A.transpose() == A).all())
        deg = sparse_graph + lap  # Recall that L=D-A (modified for weighted where D_ii is sum of edge weights and A_ij is the weight of particular edge)
        deg.data = 1 / np.sqrt(deg.data)  ##inv sqrt of degree matrix
        deg[deg == np.inf] = 0
        norm_lap = csgraph.laplacian(sparse_graph, normed=True)  # returns symmetric normalized D^-.5 xL x D^-.5
        Id = np.zeros((N, N), float)
        np.fill_diagonal(Id, 1)
        norm_lap = scipy.sparse.csr_matrix.todense(norm_lap)

        eig_val, eig_vec = np.linalg.eig(
            norm_lap)  # eig_vec[:,i] is eigenvector for eigenvalue eig_val[i] not eigh as this is only for symmetric. the eig vecs are not in decsending order
        # print('eig val', eig_val.shape, eig_val)
        if number_eig == 0: number_eig = eig_vec.shape[1]
        # print('number of eig vec', number_eig)
        Greens_matrix = np.zeros((N, N), float)
        beta_norm_lap = np.zeros((N, N), float)
        Xu = np.zeros((N, N))
        Xu[:, root] = 1
        Id_Xv = np.zeros((N, N), int)
        np.fill_diagonal(Id_Xv, 1)
        Xv_Xu = Id_Xv - Xu
        start_ = 0
        if alpha_teleport == 1:
            start_ = 1  # if there are no jumps (alph_teleport ==1), then the first term in beta-normalized Green's function will have 0 in denominator (first eigenvalue==0)

        for i in range(start_, number_eig):  # 0 instead of 1th eg

            vec_i = eig_vec[:, i]
            factor = beta_teleport + 2 * eig_val[i] * x_lazy * (1 - beta_teleport)

            vec_i = np.reshape(vec_i, (-1, 1))
            eigen_vec_mult = vec_i.dot(vec_i.T)
            Greens_matrix = Greens_matrix + (
                    eigen_vec_mult / factor)  # Greens function is the inverse of the beta-normalized laplacian
            beta_norm_lap = beta_norm_lap + (eigen_vec_mult * factor)  # beta-normalized laplacian

        deg = scipy.sparse.csr_matrix.todense(deg)

        temp = Greens_matrix.dot(deg)
        temp = deg.dot(temp) * beta_teleport
        hitting_matrix = np.zeros((N, N), float)
        diag_row = np.diagonal(temp)
        for i in range(N):
            hitting_matrix[i, :] = diag_row - temp[i, :]

        roundtrip_commute_matrix = hitting_matrix + hitting_matrix.T
        temp = Xv_Xu.dot(temp)
        final_hitting_times = np.diagonal(
            temp)  ## number_eig x 1 vector of hitting times from root (u) to number_eig of other nodes
        roundtrip_times = roundtrip_commute_matrix[root, :]
        return abs(final_hitting_times), roundtrip_times

    def prob_reaching_terminal_state1(self, terminal_state, all_terminal_states, A, root, pt, num_sim, q,
                                      cumstateChangeHist, cumstateChangeHist_all, seed):
        np.random.seed(seed)

        n_states = A.shape[0]
        n_components, labels = connected_components(csgraph=csr_matrix(A), directed=False)

        A = A / (np.max(A))
        # A[A<=0.05]=0
        jj = 0
        for row in A:
            if np.all(row == 0): A[jj, jj] = 1
            jj = jj + 1

        P = A / A.sum(axis=1).reshape((n_states, 1))

        # if P.shape[0]>16:
        #    print("P 16", P[:,16])
        n_steps = int(2 * n_states)  # 2
        currentState = root
        state = np.zeros((1, n_states))
        state[0, currentState] = 1
        currentState = root
        state = np.zeros((1, n_states))
        state[0, currentState] = 1
        state_root = state.copy()
        neigh_terminal = np.where(A[:, terminal_state] > 0)[0]
        non_nn_terminal_state = []
        for ts_i in all_terminal_states:
            if pt[ts_i] > pt[terminal_state]: non_nn_terminal_state.append(ts_i)

        for ts_i in all_terminal_states:
            if np.all(neigh_terminal != ts_i): non_nn_terminal_state.append(ts_i)
            # print(ts_i, 'is a non-neighbor terminal state to the target terminal', terminal_state)

        # cumstateChangeHist = np.zeros((1, n_states))
        # cumstateChangeHist_all = np.zeros((1, n_states))
        count_reach_terminal_state = 0
        count_r = 0
        for i in range(num_sim):
            # distr_hist = [[0 for i in range(n_states)]]
            stateChangeHist = np.zeros((n_states, n_states))
            stateChangeHist[root, root] = 1
            state = state_root
            currentState = root
            stateHist = state
            terminal_state_found = False
            non_neighbor_terminal_state_reached = False
            # print('root', root)
            # print('terminal state target', terminal_state)

            x = 0
            while (x < n_steps) & (
                    (terminal_state_found == False)):  # & (non_neighbor_terminal_state_reached == False)):
                currentRow = np.ma.masked_values((P[currentState]), 0.0)
                nextState = simulate_multinomial(currentRow)
                # print('next state', nextState)
                if nextState == terminal_state:
                    terminal_state_found = True
                    count_r = count_r + 1
                    # print('terminal state found at step', x)
                # if nextState in non_nn_terminal_state:
                # non_neighbor_terminal_state_reached = True
                # Keep track of state changes
                stateChangeHist[currentState, nextState] += 1
                # Keep track of the state vector itself
                state = np.zeros((1, n_states))
                state[0, nextState] = 1.0
                # Keep track of state history
                stateHist = np.append(stateHist, state, axis=0)
                currentState = nextState
                x = x + 1

            if (terminal_state_found == True):
                cumstateChangeHist = cumstateChangeHist + np.any(
                    stateChangeHist > 0, axis=0)
                count_reach_terminal_state = count_reach_terminal_state + 1
            cumstateChangeHist_all = cumstateChangeHist_all + np.any(
                stateChangeHist > 0, axis=0)
            # avoid division by zero on states that were never reached (e.g. terminal states that come after the target terminal state)

        cumstateChangeHist_all[cumstateChangeHist_all == 0] = 1
        prob_ = cumstateChangeHist / cumstateChangeHist_all

        np.set_printoptions(precision=3)
        q.append([cumstateChangeHist, cumstateChangeHist_all])

    def simulate_markov_sub(self, A, num_sim, hitting_array, q, root):
        n_states = A.shape[0]
        P = A / A.sum(axis=1).reshape((n_states, 1))
        # hitting_array = np.ones((P.shape[0], 1)) * 1000
        hitting_array_temp = np.zeros((P.shape[0], 1)).astype('float64')
        n_steps = int(2 * n_states)
        hitting_array_final = np.zeros((1, n_states))
        currentState = root

        print('root is', root)
        state = np.zeros((1, n_states))
        state[0, currentState] = 1
        state_root = state.copy()
        for i in range(num_sim):
            dist_list = []
            # print(i, 'th simulation in Markov')
            # if i % 10 == 0: print(i, 'th simulation in Markov', time.ctime())
            state = state_root
            currentState = root
            stateHist = state
            for x in range(n_steps):
                currentRow = np.ma.masked_values((P[currentState]), 0.0)
                nextState = simulate_multinomial(currentRow)
                dist = A[currentState, nextState]

                dist = (1 / ((1 + math.exp((dist - 1)))))

                dist_list.append(dist)
                # print('next state', nextState)
                # Keep track of state changes
                # stateChangeHist[currentState,nextState]+=1
                # Keep track of the state vector itself
                state = np.zeros((1, n_states))
                state[0, nextState] = 1.0

                currentState = nextState

                # Keep track of state history
                stateHist = np.append(stateHist, state, axis=0)

            for state_i in range(P.shape[0]):
                # print('first reach state', state_i, 'at step', np.where(stateHist[:, state_i] == 1)[0][0])
                first_time_at_statei = np.where(stateHist[:, state_i] == 1)[0]
                if len(first_time_at_statei) == 0:
                    # print('did not reach state', state_i,'setting dummy path length')
                    hitting_array_temp[state_i, 0] = n_steps + 1
                else:
                    total_dist = 0
                    for ff in range(first_time_at_statei[0]):
                        total_dist = dist_list[ff] + total_dist

                    hitting_array_temp[state_i, 0] = total_dist  # first_time_at_statei[0]

            # hitting_array_temp[hitting_array_temp==(n_steps+1)] = np.mean(hitting_array_temp[hitting_array_temp!=n_steps+1])

            hitting_array = np.append(hitting_array, hitting_array_temp, axis=1)
            # print('hitting temp', hitting_array_temp)
            # if i % 100 == 0: print(i, 'th','has hitting temp', hitting_array_temp.flatten())
        hitting_array = hitting_array[:, 1:]
        q.append(hitting_array)

    def simulate_branch_probability(self, terminal_state, all_terminal_states, A, root, pt, num_sim=300):
        print('root', root)
        print('terminal state target', terminal_state)
        n_states = A.shape[0]

        ncpu = multiprocessing.cpu_count()
        if (ncpu == 1) | (ncpu == 2):
            n_jobs = 1
        elif ncpu > 2:
            n_jobs = min(ncpu - 1, 5)
        print('njobs', n_jobs)
        num_sim_pp = int(num_sim / n_jobs)  # num of simulations per process
        print('num_sim_pp', num_sim_pp)

        jobs = []

        manager = multiprocessing.Manager()

        q = manager.list()
        seed_list = list(range(n_jobs))
        for i in range(n_jobs):
            cumstateChangeHist = np.zeros((1, n_states))
            cumstateChangeHist_all = np.zeros((1, n_states))
            process = multiprocessing.Process(target=self.prob_reaching_terminal_state1, args=(
            terminal_state, all_terminal_states, A, root, pt, num_sim_pp, q, cumstateChangeHist, cumstateChangeHist_all,
            seed_list[i]))
            jobs.append(process)

        for j in jobs:
            j.start()

        for j in jobs:
            j.join()

        cumhistory_vec = q[0][0]
        cumhistory_vec_all = q[0][1]

        count_reached = cumhistory_vec_all[0, terminal_state]

        for i in range(1, len(q)):  # [1,2,3,4]:
            # for qi in q[1:]:
            cumhistory_vec = cumhistory_vec + q[i][0]
            cumhistory_vec_all = cumhistory_vec_all + q[i][1]

            # hitting_array = np.append(hitting_array, qi, axis=1)  # .get(), axis=1)
            count_reached = count_reached + q[i][1][0, terminal_state]

        print('accumulated number of times Terminal state', terminal_state, 'is found:', count_reached)
        # print('cumhistory_vec', cumhistory_vec)
        # print('cumhistory_vec_all', cumhistory_vec_all)
        cumhistory_vec_all[cumhistory_vec_all == 0] = 1
        prob_ = cumhistory_vec / cumhistory_vec_all

        np.set_printoptions(precision=3)

        # print('prob', prob_)
        if count_reached == 0:
            prob_[:, terminal_state] = 0
            print('never reached state', terminal_state)
        else:
            loc_1 = np.where(prob_ == 1)

            loc_1 = loc_1[1]
            print('loc_1', loc_1)
            # prob_[0, terminal_state] = 0  # starting at the root, index=0
            prob_[0, loc_1] = 0
            # print('zerod out prob', prob_)
            temp_ = np.max(prob_)
            if temp_ == 0: temp_ = 1
            prob_ = prob_ / min(1, 1.1 * temp_)
        # prob_[0, terminal_state] = 1
        prob_[0, loc_1] = 1
        # prob_ = np.sqrt(prob_)
        print('np.max', np.max(prob_))
        # prob_ = prob_/np.max(prob_)
        print('scaled prob', prob_)
        return list(prob_)[0]

    def simulate_markov(self, A, root):

        n_states = A.shape[0]
        P = A / A.sum(axis=1).reshape((n_states, 1))
        # print('row normed P',P.shape, P, P.sum(axis=1))
        x_lazy = self.x_lazy  # 1-x is prob lazy
        alpha_teleport = self.alpha_teleport
        # bias_P is the transition probability matrix

        # P = x_lazy * P + (1 - x_lazy) * np.identity(n_states)
        # print(P, P.sum(axis=1))
        # P = alpha_teleport * P + ((1 - alpha_teleport) * (1 / n_states) * (np.ones((n_states, n_states))))
        # print('check prob of each row sum to one', P.sum(axis=1))

        currentState = root
        state = np.zeros((1, n_states))
        state[0, currentState] = 1
        state_root = state.copy()
        stateHist = state
        dfStateHist = pd.DataFrame(state)
        distr_hist = np.zeros([1, n_states])
        num_sim = 1300  # 1000  # 1300

        ncpu = multiprocessing.cpu_count()
        if (ncpu == 1) | (ncpu == 2):
            n_jobs = 1
        elif ncpu > 2:
            n_jobs = min(ncpu - 1, 5)
        print('njobs', n_jobs)
        num_sim_pp = int(num_sim / n_jobs)  # num of simulations per process
        print('num_sim_pp', num_sim_pp)

        n_steps = int(2 * n_states)

        jobs = []

        manager = multiprocessing.Manager()

        q = manager.list()
        for i in range(n_jobs):
            hitting_array = np.ones((P.shape[0], 1)) * 1000
            process = multiprocessing.Process(target=self.simulate_markov_sub,
                                              args=(P, num_sim_pp, hitting_array, q, root))
            jobs.append(process)

        for j in jobs:
            j.start()

        for j in jobs:
            j.join()

        print('ended all multiprocesses, will retrieve and reshape')
        hitting_array = q[0]
        for qi in q[1:]:
            hitting_array = np.append(hitting_array, qi, axis=1)  # .get(), axis=1)
        print('finished getting from queue', hitting_array.shape)
        hitting_array_final = np.zeros((1, n_states))
        no_times_state_reached_array = np.zeros((1, n_states))

        for i in range(n_states):
            rowtemp = hitting_array[i, :]
            no_times_state_reached_array[0, i] = np.sum(rowtemp != (n_steps + 1))
        lower_quart = np.percentile(no_times_state_reached_array, 25)
        # loc_rarely_reached = np.where(no_times_state_reached_array<= upper_quart)
        # print('rarely reached clus', loc_rarely_reached, upper_quart, no_times_state_reached_array)
        for i in range(n_states):
            rowtemp = hitting_array[i, :]
            no_times_state_reached = np.sum(rowtemp != (n_steps + 1))
            if no_times_state_reached != 0:
                # print('the number of times state ',i, 'has been reached is', no_times_state_reached )
                # if no_times_state_reached < lower_quart:
                # perc = np.percentile(rowtemp[rowtemp != n_steps + 1], 5) + 0.001
                # print('in lower quart for state', i)

                perc = np.percentile(rowtemp[rowtemp != n_steps + 1], 15) + 0.001  # 15 for Human and Toy
                # print('state ', i,' has perc' ,perc)

                # print('smaller than perc', rowtemp[rowtemp <= perc])

                # hitting_array_final[0, i] = np.min(rowtemp[rowtemp != (n_steps + 1)])
                hitting_array_final[0, i] = np.mean(rowtemp[rowtemp <= perc])
            else:
                hitting_array_final[0, i] = (n_steps + 1)

        # hitting_array=np.mean(hitting_array, axis=1)
        print('hitting from sim markov', [(i, val) for i, val in enumerate(hitting_array_final.flatten())])
        return hitting_array_final[0]

    def compute_hitting_time_onbias(self, laplacian, inv_sqr_deg, root, x_lazy, alpha_teleport, number_eig=0):
        # 1- alpha is the probabilty of teleporting
        # 1- x_lazy is the probability of staying in current state (be lazy)
        beta_teleport = 2 * (1 - alpha_teleport) / (2 - alpha_teleport)
        N = laplacian.shape[0]
        print('is laplacian of biased symmetric', (laplacian.transpose() == laplacian).all())
        Id = np.zeros((N, N), float)
        np.fill_diagonal(Id, 1)
        # norm_lap = scipy.sparse.csr_matrix.todense(laplacian)

        eig_val, eig_vec = np.linalg.eig(
            laplacian)  # eig_vec[:,i] is eigenvector for eigenvalue eig_val[i] not eigh as this is only for symmetric. the eig vecs are not in decsending order
        print('eig val', eig_val.shape)
        if number_eig == 0: number_eig = eig_vec.shape[1]
        print('number of eig vec', number_eig)
        Greens_matrix = np.zeros((N, N), float)
        beta_norm_lap = np.zeros((N, N), float)
        Xu = np.zeros((N, N))
        Xu[:, root] = 1
        Id_Xv = np.zeros((N, N), int)
        np.fill_diagonal(Id_Xv, 1)
        Xv_Xu = Id_Xv - Xu
        start_ = 0
        if alpha_teleport == 1:
            start_ = 1  # if there are no jumps (alph_teleport ==1), then the first term in beta-normalized Green's function will have 0 in denominator (first eigenvalue==0)

        for i in range(start_, number_eig):  # 0 instead of 1th eg
            # print(i, 'th eigenvalue is', eig_val[i])
            vec_i = eig_vec[:, i]
            factor = beta_teleport + 2 * eig_val[i] * x_lazy * (1 - beta_teleport)
            # print('factor', 1 / factor)

            vec_i = np.reshape(vec_i, (-1, 1))
            eigen_vec_mult = vec_i.dot(vec_i.T)
            Greens_matrix = Greens_matrix + (
                    eigen_vec_mult / factor)  # Greens function is the inverse of the beta-normalized laplacian
            beta_norm_lap = beta_norm_lap + (eigen_vec_mult * factor)  # beta-normalized laplacian

        temp = Greens_matrix.dot(inv_sqr_deg)
        temp = inv_sqr_deg.dot(temp) * beta_teleport
        hitting_matrix = np.zeros((N, N), float)
        diag_row = np.diagonal(temp)
        for i in range(N):
            hitting_matrix[i, :] = diag_row - temp[i, :]

        roundtrip_commute_matrix = hitting_matrix + hitting_matrix.T
        temp = Xv_Xu.dot(temp)
        final_hitting_times = np.diagonal(
            temp)  ## number_eig x 1 vector of hitting times from root (u) to number_eig of other nodes
        roundtrip_times = roundtrip_commute_matrix[root, :]
        return abs(final_hitting_times), roundtrip_times

    def project_hittingtimes_sc(self, pt):
        if self.data.shape[0] > 1000:
            knn_sc = 10
        else:
            knn_sc = 10
        neighbor_array, distance_array = self.knn_struct.knn_query(self.data, k=knn_sc)
        print('shape of neighbor in project onto sc', neighbor_array.shape)
        labels = np.asarray(self.labels)
        sc_pt = np.zeros((len(self.labels),))

        i = 0
        for row in neighbor_array:
            mean_weight = 0
            # print('row in neighbor array of cells', row, labels.shape)
            neighboring_clus = labels[row]
            # print('neighbor clusters labels', neighboring_clus)
            for clus_i in set(list(neighboring_clus)):
                hitting_time_clus_i = pt[clus_i]
                num_clus_i = np.sum(neighboring_clus == clus_i)
                # if clus_i == self.root[0]: print('root is a neighbor', pt[clus_i], 'num NN cells beloning to root',            num_clus_i)
                # print('hitting and num_clus for Clusi', hitting_time_clus_i, num_clus_i)
                mean_weight = mean_weight + hitting_time_clus_i * num_clus_i / knn_sc
                # print('mean weight',mean_weight)
            sc_pt[i] = mean_weight
            # if self.root[0] in set(list(neighboring_clus)): print('the mean sc time for root neighbor is', mean_weight)
            i = i + 1
        return sc_pt

    def project_branch_probability_sc(self, bp_array_clus, pt):
        if self.data.shape[0] > 1000:
            knn_sc = 10
        else:
            knn_sc = 10

        neighbor_array, distance_array = self.knn_struct.knn_query(self.data, k=knn_sc)
        print('shape of neighbor in project onto sc', neighbor_array.shape)
        labels = np.asarray(self.labels)
        n_clus = len(list(set(labels)))

        weight_array = np.zeros((len(labels), n_clus))

        for irow, row in enumerate(neighbor_array):
            mean_weight = 0
            # print('row in neighbor array of cells', row, labels.shape)
            neighboring_clus = labels[row]

            for clus_i in set(list(neighboring_clus)):
                # hitting_time_clus_i = df_graph[clus_i]
                num_clus_i = np.sum(neighboring_clus == clus_i)
                # print('hitting and num_clus for Clusi', hitting_time_clus_i, num_clus_i)
                wi = num_clus_i / knn_sc
                weight_array[irow, clus_i] = wi
                # print('mean weight',mean_weight)
            # print('rowi of weight array', weight_array[irow,:])
        # print('shape weight array', weight_array)
        # print(weight_array)
        bp_array_sc = weight_array.dot(bp_array_clus)
        bp_array_sc = bp_array_sc * 1. / np.max(bp_array_sc, axis=0)  # divide cell by max value in that column
        # print('column max:',np.max(bp_array_sc, axis=0))
        # print('sc bp array max', np.max(bp_array_sc))
        # bp_array_sc = bp_array_sc/np.max(bp_array_sc)
        for i, label_ts in enumerate(list(self.terminal_clusters)):

            loc_i = np.where(np.asarray(self.labels) == label_ts)[0]
            loc_noti = np.where(np.asarray(self.labels) != label_ts)[0]
            if np.max(bp_array_sc[loc_noti, i]) > 0.8: bp_array_sc[loc_i, i] = 1.2
        pt = np.asarray(pt)
        pt = np.reshape(pt, (n_clus, 1))
        pt_sc = weight_array.dot(pt)

        self.single_cell_bp = bp_array_sc
        self.single_cell_pt_markov = pt_sc.flatten()

        return

    def make_knn_struct(self, too_big=False, big_cluster=None, visual=False, data_visual=None):
        if visual == False:
            data = self.data
        else:
            data = data_visual
        if self.knn > 190: print(colored('please provide a lower K_in for KNN graph construction', 'red'))
        ef_query = max(100, self.knn + 1)  # ef always should be >K. higher ef, more accuate query
        if too_big == False:
            num_dims = data.shape[1]
            n_elements = data.shape[0]
            p = hnswlib.Index(space=self.distance, dim=num_dims)  # default to Euclidean distance
            p.set_num_threads(self.num_threads)  # allow user to set threads used in KNN construction
            if n_elements < 10000:
                ef_param_const = min(n_elements - 10, 500)
                ef_query = ef_param_const
                print('setting ef_construction to', )
            else:
                ef_param_const = 200

            if (num_dims > 30) & (n_elements <= 50000):
                p.init_index(max_elements=n_elements, ef_construction=ef_param_const,
                             M=48)  ## good for scRNA seq where dimensionality is high
            else:
                p.init_index(max_elements=n_elements, ef_construction=ef_param_const, M=30)
            p.add_items(data)
        if too_big == True:
            num_dims = big_cluster.shape[1]
            n_elements = big_cluster.shape[0]
            p = hnswlib.Index(space='l2', dim=num_dims)
            p.init_index(max_elements=n_elements, ef_construction=200, M=30)
            p.add_items(big_cluster)
        p.set_ef(ef_query)  # ef should always be > k
        return p

    def make_csrmatrix_noselfloop(self, neighbor_array, distance_array, auto_=True):
        if auto_ == True:
            local_pruning_bool = not (self.keep_all_local_dist)
            if local_pruning_bool == True: print(colored('commencing local pruning based on l2 (squared) at', 'blue'),
                                                 colored(str(self.dist_std_local) + 's.dev above mean', 'green'))
        if auto_ == False: local_pruning_bool = False

        row_list = []
        col_list = []
        weight_list = []
        neighbor_array = neighbor_array  # not listed in in any order of proximity
        # print('size neighbor array', neighbor_array.shape)
        num_neigh = neighbor_array.shape[1]
        distance_array = np.sqrt(distance_array)
        n_neighbors = neighbor_array.shape[1]
        n_cells = neighbor_array.shape[0]
        rowi = 0
        count_0dist = 0
        discard_count = 0

        if local_pruning_bool == True:  # do some local pruning based on distance
            for row in neighbor_array:
                distlist = distance_array[rowi, :]
                to_keep = np.where(distlist <= np.mean(distlist) + self.dist_std_local * np.std(distlist))[0]  # 0*std
                updated_nn_ind = row[np.ix_(to_keep)]
                updated_nn_weights = distlist[np.ix_(to_keep)]
                discard_count = discard_count + (num_neigh - len(to_keep))

                for ik in range(len(updated_nn_ind)):
                    if rowi != row[ik]:  # remove self-loops
                        row_list.append(rowi)
                        col_list.append(updated_nn_ind[ik])
                        dist = updated_nn_weights[ik]
                        if dist == 0:
                            count_0dist = count_0dist + 1
                        weight_list.append(dist)

                rowi = rowi + 1
        weight_list = np.asarray(weight_list)
        weight_list = 1. / (weight_list + 0.01)  # 0.05
        if local_pruning_bool == False:  # dont prune based on distance
            row_list.extend(list(np.transpose(np.ones((n_neighbors, n_cells)) * range(0, n_cells)).flatten()))
            col_list = neighbor_array.flatten().tolist()
            # distance_array = np.sqrt(distance_array)
            weight_list = (1. / (distance_array.flatten() + 0.01))
        print('weight list ', np.percentile(np.asarray(weight_list), 5), np.percentile(np.asarray(weight_list), 95))
        # if local_pruning_bool == True: print('share of neighbors discarded in local distance pruning %.1f' % (discard_count / neighbor_array.size))

        weight_list = weight_list * (np.mean(distance_array) ** 2)
        print('mean distance array in make csr matrix', np.mean(distance_array))
        weight_list = weight_list.tolist()
        print('weight list ', np.percentile(np.asarray(weight_list), 5), np.percentile(np.asarray(weight_list), 95))
        csr_graph = csr_matrix((np.array(weight_list), (np.array(row_list), np.array(col_list))),
                               shape=(n_cells, n_cells))
        return csr_graph

    def func_mode(self, ll):
        # return MODE of list
        # If multiple items are maximal, the function returns the first one encountered.
        return max(set(ll), key=ll.count)

    def run_toobig_subPARC(self, X_data, jac_std_toobig=1,
                           jac_weighted_edges=True):
        n_elements = X_data.shape[0]
        hnsw = self.make_knn_struct(too_big=True, big_cluster=X_data)
        if self.knn >= 0.8 * n_elements:
            k = int(0.5 * n_elements)
        else:
            k = self.knn
        neighbor_array, distance_array = hnsw.knn_query(X_data, k=k)

        # print('shapes of neigh and dist array', neighbor_array.shape, distance_array.shape)
        csr_array = self.make_csrmatrix_noselfloop(neighbor_array, distance_array)
        sources, targets = csr_array.nonzero()
        mask = np.zeros(len(sources), dtype=bool)
        mask |= (csr_array.data > (
                np.mean(csr_array.data) + np.std(csr_array.data) * 5))  # smaller distance means stronger edge
        # print('sum of mask', sum(mask))
        csr_array.data[mask] = 0
        csr_array.eliminate_zeros()
        sources, targets = csr_array.nonzero()
        edgelist = list(zip(sources.tolist(), targets.tolist()))
        edgelist_copy = edgelist.copy()
        G = ig.Graph(edgelist, edge_attrs={'weight': csr_array.data.tolist()})
        sim_list = G.similarity_jaccard(pairs=edgelist_copy)  # list of jaccard weights
        new_edgelist = []
        sim_list_array = np.asarray(sim_list)
        if jac_std_toobig == 'median':
            threshold = np.median(sim_list)
        else:
            threshold = np.mean(sim_list) - jac_std_toobig * np.std(sim_list)
        strong_locs = np.where(sim_list_array > threshold)[0]
        for ii in strong_locs: new_edgelist.append(edgelist_copy[ii])
        sim_list_new = list(sim_list_array[strong_locs])

        if jac_weighted_edges == True:
            G_sim = ig.Graph(n=n_elements, edges=list(new_edgelist), edge_attrs={'weight': sim_list_new})
        else:
            G_sim = ig.Graph(n=n_elements, edges=list(new_edgelist))
        G_sim.simplify(combine_edges='sum')
        resolution_parameter = 1
        if jac_weighted_edges == True:
            partition = leidenalg.find_partition(G_sim, leidenalg.ModularityVertexPartition, weights='weight',
                                                 n_iterations=self.n_iter_leiden, seed=self.random_seed)
        else:
            partition = leidenalg.find_partition(G_sim, leidenalg.ModularityVertexPartition,
                                                 n_iterations=self.n_iter_leiden, seed=self.random_seed)
        # print('Q= %.2f' % partition.quality())
        PARC_labels_leiden = np.asarray(partition.membership)
        PARC_labels_leiden = np.reshape(PARC_labels_leiden, (n_elements, 1))
        small_pop_list = []
        small_cluster_list = []
        small_pop_exist = False
        dummy, PARC_labels_leiden = np.unique(list(PARC_labels_leiden.flatten()), return_inverse=True)
        for cluster in set(PARC_labels_leiden):
            population = len(np.where(PARC_labels_leiden == cluster)[0])
            if population < 5:  # <10
                small_pop_exist = True
                small_pop_list.append(list(np.where(PARC_labels_leiden == cluster)[0]))
                small_cluster_list.append(cluster)

        for small_cluster in small_pop_list:
            for single_cell in small_cluster:
                old_neighbors = neighbor_array[single_cell, :]
                group_of_old_neighbors = PARC_labels_leiden[old_neighbors]
                group_of_old_neighbors = list(group_of_old_neighbors.flatten())
                available_neighbours = set(group_of_old_neighbors) - set(small_cluster_list)
                if len(available_neighbours) > 0:
                    available_neighbours_list = [value for value in group_of_old_neighbors if
                                                 value in list(available_neighbours)]
                    best_group = max(available_neighbours_list, key=available_neighbours_list.count)
                    PARC_labels_leiden[single_cell] = best_group

        do_while_time = time.time()
        while (small_pop_exist == True) & (time.time() - do_while_time < 5):
            small_pop_list = []
            small_pop_exist = False
            for cluster in set(list(PARC_labels_leiden.flatten())):
                population = len(np.where(PARC_labels_leiden == cluster)[0])
                if population < 10:
                    small_pop_exist = True
                    # print(cluster, ' has small population of', population, )
                    small_pop_list.append(np.where(PARC_labels_leiden == cluster)[0])
            for small_cluster in small_pop_list:
                for single_cell in small_cluster:
                    old_neighbors = neighbor_array[single_cell, :]
                    group_of_old_neighbors = PARC_labels_leiden[old_neighbors]
                    group_of_old_neighbors = list(group_of_old_neighbors.flatten())
                    best_group = max(set(group_of_old_neighbors), key=group_of_old_neighbors.count)
                    PARC_labels_leiden[single_cell] = best_group

        dummy, PARC_labels_leiden = np.unique(list(PARC_labels_leiden.flatten()), return_inverse=True)
        self.labels = PARC_labels_leiden
        print('finished run_toobig', time.ctime())
        return PARC_labels_leiden

    def recompute_weights(self, clustergraph_ig, pop_list_raw):
        sparse_clustergraph = get_sparse_from_igraph(clustergraph_ig, weight_attr='weight')
        n = sparse_clustergraph.shape[0]
        sources, targets = sparse_clustergraph.nonzero()
        edgelist = list(zip(sources, targets))
        weights = sparse_clustergraph.data

        new_weights = []
        i = 0
        for s, t in edgelist:
            pop_s = pop_list_raw[s]
            pop_t = pop_list_raw[t]
            w = weights[i]
            nw = w * (pop_s + pop_t) / (pop_s * pop_t)  # *
            new_weights.append(nw)

            i = i + 1
            scale_factor = max(new_weights) - min(new_weights)
            wmin = min(new_weights)

        new_weights = [(wi + wmin) / scale_factor for wi in new_weights]

        sparse_clustergraph = csr_matrix((np.array(new_weights), (sources, targets)), shape=(n, n))

        sources, targets = sparse_clustergraph.nonzero()
        edgelist = list(zip(sources, targets))
        return sparse_clustergraph, edgelist

    def find_root_HumanCD34(self, graph_dense, PARC_labels_leiden, root_idx, true_labels):
        majority_truth_labels = np.empty((len(PARC_labels_leiden), 1), dtype=object)
        graph_node_label = []
        true_labels = np.asarray(true_labels)

        deg_list = graph_dense.sum(axis=1).reshape((1, -1)).tolist()[0]

        for ci, cluster_i in enumerate(sorted(list(set(PARC_labels_leiden)))):
            cluster_i_loc = np.where(np.asarray(PARC_labels_leiden) == cluster_i)[0]

            majority_truth = self.func_mode(list(true_labels[cluster_i_loc]))

            majority_truth_labels[cluster_i_loc] = str(majority_truth) + 'c' + str(cluster_i)

            graph_node_label.append(str(majority_truth) + 'c' + str(cluster_i))
            root = PARC_labels_leiden[root_idx]
        return graph_node_label, majority_truth_labels, deg_list, root

    def find_root_bcell(self, graph_dense, PARC_labels_leiden, root_user, true_labels):
        majority_truth_labels = np.empty((len(PARC_labels_leiden), 1), dtype=object)
        graph_node_label = []
        true_labels = np.asarray(true_labels)

        deg_list = graph_dense.sum(axis=1).reshape((1, -1)).tolist()[0]

        for ci, cluster_i in enumerate(sorted(list(set(PARC_labels_leiden)))):
            # print('cluster i', cluster_i)
            cluster_i_loc = np.where(np.asarray(PARC_labels_leiden) == cluster_i)[0]

            majority_truth = self.func_mode(list(true_labels[cluster_i_loc]))

            majority_truth_labels[cluster_i_loc] = str(majority_truth) + 'c' + str(cluster_i)

            graph_node_label.append(str(majority_truth) + 'c' + str(cluster_i))
        root = PARC_labels_leiden[root_user]
        return graph_node_label, majority_truth_labels, deg_list, root

    def find_root_iPSC(self, graph_dense, PARC_labels_leiden, root_user, true_labels, super_cluster_labels_sub,
                       super_node_degree_list):
        majority_truth_labels = np.empty((len(PARC_labels_leiden), 1), dtype=object)
        graph_node_label = []
        min_deg = 1000
        super_min_deg = 1000
        found_super_and_sub_root = False
        found_any_root = False
        true_labels = np.asarray(true_labels)

        deg_list = graph_dense.sum(axis=1).reshape((1, -1)).tolist()[0]

        print('deg list', deg_list)  # locallytrimmed_g.degree()

        for ci, cluster_i in enumerate(sorted(list(set(PARC_labels_leiden)))):

            cluster_i_loc = np.where(np.asarray(PARC_labels_leiden) == cluster_i)[0]

            majority_truth = str(self.func_mode(list(true_labels[cluster_i_loc])))

            if self.super_cluster_labels != False:
                super_majority_cluster = self.func_mode(list(np.asarray(super_cluster_labels_sub)[cluster_i_loc]))
                super_majority_cluster_loc = np.where(np.asarray(super_cluster_labels_sub) == super_majority_cluster)[0]
                super_majority_truth = self.func_mode(list(true_labels[super_majority_cluster_loc]))

                super_node_degree = super_node_degree_list[super_majority_cluster]

                if (str(root_user) == majority_truth) & (str(root_user) == str(super_majority_truth)):
                    if super_node_degree < super_min_deg:
                        found_super_and_sub_root = True
                        root = cluster_i
                        found_any_root = True
                        min_deg = deg_list[ci]
                        super_min_deg = super_node_degree
                        print('new root is', root, ' with degree', min_deg, 'and super node degree',
                              super_min_deg)
            majority_truth_labels[cluster_i_loc] = str(majority_truth) + 'c' + str(cluster_i)

            graph_node_label.append(str(majority_truth) + 'c' + str(cluster_i))
        if (self.super_cluster_labels == False) | (found_super_and_sub_root == False):
            print('self.super_cluster_labels', super_cluster_labels_sub, ' foundsuper_cluster_sub and super root',
                  found_super_and_sub_root)
            for ic, cluster_i in enumerate(sorted(list(set(PARC_labels_leiden)))):
                cluster_i_loc = np.where(np.asarray(PARC_labels_leiden) == cluster_i)[0]
                print('cluster', cluster_i, 'set true labels', set(true_labels))
                true_labels = np.asarray(true_labels)

                majority_truth = str(self.func_mode(list(true_labels[cluster_i_loc])))
                print('cluster', cluster_i, 'has majority', majority_truth, 'with degree list', deg_list)
                if (str(root_user) == str(majority_truth)):
                    print('did not find a super and sub cluster with majority ', root_user)
                    if deg_list[ic] < min_deg:
                        root = cluster_i
                        found_any_root = True
                        min_deg = deg_list[ic]
                        print('new root is', root, ' with degree', min_deg, majority_truth)
        # print('len graph node label', graph_node_label)
        if found_any_root == False:
            print('setting arbitrary root', cluster_i)
            root = cluster_i
        return graph_node_label, majority_truth_labels, deg_list, root

    def find_root(self, graph_dense, PARC_labels_leiden, root_user, true_labels, super_cluster_labels_sub,
                  super_node_degree_list):
        majority_truth_labels = np.empty((len(PARC_labels_leiden), 1), dtype=object)
        graph_node_label = []
        min_deg = 1000
        super_min_deg = 1000
        found_super_and_sub_root = False
        found_any_root = False
        true_labels = np.asarray(true_labels)

        deg_list = graph_dense.sum(axis=1).reshape((1, -1)).tolist()[0]

        print('deg list', deg_list)  # locallytrimmed_g.degree()

        for ci, cluster_i in enumerate(sorted(list(set(PARC_labels_leiden)))):

            cluster_i_loc = np.where(np.asarray(PARC_labels_leiden) == cluster_i)[0]

            majority_truth = str(self.func_mode(list(true_labels[cluster_i_loc])))

            if self.super_cluster_labels != False:
                super_majority_cluster = self.func_mode(list(np.asarray(super_cluster_labels_sub)[cluster_i_loc]))
                super_majority_cluster_loc = np.where(np.asarray(super_cluster_labels_sub) == super_majority_cluster)[0]
                super_majority_truth = self.func_mode(list(true_labels[super_majority_cluster_loc]))

                super_node_degree = super_node_degree_list[super_majority_cluster]

                if (str(root_user) in majority_truth) & (str(root_user) in str(super_majority_truth)):
                    if super_node_degree < super_min_deg:
                        found_super_and_sub_root = True
                        root = cluster_i
                        found_any_root = True
                        min_deg = deg_list[ci]
                        super_min_deg = super_node_degree
                        print('new root is', root, ' with degree', min_deg, 'and super node degree',
                              super_min_deg)
            majority_truth_labels[cluster_i_loc] = str(majority_truth) + 'c' + str(cluster_i)

            graph_node_label.append(str(majority_truth) + 'c' + str(cluster_i))
        if (self.super_cluster_labels == False) | (found_super_and_sub_root == False):
            print('self.super_cluster_labels', super_cluster_labels_sub, ' foundsuper_cluster_sub and super root',
                  found_super_and_sub_root)
            for ic, cluster_i in enumerate(sorted(list(set(PARC_labels_leiden)))):
                cluster_i_loc = np.where(np.asarray(PARC_labels_leiden) == cluster_i)[0]
                print('cluster', cluster_i, 'set true labels', set(true_labels))
                true_labels = np.asarray(true_labels)

                majority_truth = str(self.func_mode(list(true_labels[cluster_i_loc])))
                print('cluster', cluster_i, 'has majority', majority_truth, 'with degree list', deg_list)
                print('root user and majority', root_user, majority_truth)
                if (str(root_user) in str(majority_truth)):
                    print('did not find a super and sub cluster with majority ', root_user)
                    if deg_list[ic] < min_deg:
                        root = cluster_i
                        found_any_root = True
                        min_deg = deg_list[ic]
                        print('new root is', root, ' with degree', min_deg, majority_truth)
        # print('len graph node label', graph_node_label)
        if found_any_root == False:
            print('setting arbitrary root', cluster_i)
            root = cluster_i
        return graph_node_label, majority_truth_labels, deg_list, root

    def full_graph_paths(self, X_data, n_components_original=1):
        # make igraph object of very low-K KNN using the knn_struct PCA-dimension space made in PARC.
        # This is later used by find_shortest_path for sc_bp visual
        # neighbor array is not listed in in any order of proximity
        print('number of components in the original full graph', n_components_original)
        print('for downstream visualization purposes we are also constructing a low knn-graph ')
        neighbor_array, distance_array = self.knn_struct.knn_query(X_data, k=3)
        csr_array = self.make_csrmatrix_noselfloop(neighbor_array, distance_array, auto_=False)
        n_comp, comp_labels = connected_components(csr_array, return_labels=True)
        k_0 = 3
        if n_components_original == 1:
            while (n_comp > 1):
                k_0 = k_0 + 1
                neighbor_array, distance_array = self.knn_struct.knn_query(X_data, k=k_0)
                csr_array = self.make_csrmatrix_noselfloop(neighbor_array, distance_array,
                                                           auto_=False)  # do not automatically use the local-pruning of Via
                n_comp, comp_labels = connected_components(csr_array, return_labels=True)
        if n_components_original > 1:
            while (k_0 <= 5) & (n_comp > n_components_original):
                k_0 = k_0 + 1
                neighbor_array, distance_array = self.knn_struct.knn_query(X_data, k=k_0)
                csr_array = self.make_csrmatrix_noselfloop(neighbor_array, distance_array,
                                                           auto_=False)  # do not automatically use the local-pruning of Via)
                n_comp, comp_labels = connected_components(csr_array, return_labels=True)
        row_list = []

        print('size neighbor array in low-KNN in pca-space for visualization', neighbor_array.shape)
        n_neighbors = neighbor_array.shape[1]
        n_cells = neighbor_array.shape[0]

        row_list.extend(list(np.transpose(np.ones((n_neighbors, n_cells)) * range(0, n_cells)).flatten()))
        col_list = neighbor_array.flatten().tolist()
        weight_list = (distance_array.flatten()).tolist()
        csr_full_graph = csr_matrix((np.array(weight_list), (np.array(row_list), np.array(col_list))),
                                    shape=(n_cells, n_cells))

        sources, targets = csr_full_graph.nonzero()
        edgelist = list(zip(sources.tolist(), targets.tolist()))
        Gr = ig.Graph(edgelist)  # , edge_attrs={'weight': csr_full_graph.data.tolist()})
        Gr.simplify(combine_edges='sum')
        return Gr

    def get_gene_expression(self, gene_exp, title_gene=""):

        fig_0, ax = plt.subplots()
        sc_pt = self.single_cell_pt_markov
        sc_bp_original = self.single_cell_bp
        n_terminal_states = sc_bp_original.shape[1]

        jet = cm.get_cmap('jet', n_terminal_states)
        cmap_ = jet(range(n_terminal_states))

        for i in range(n_terminal_states):
            sc_bp = sc_bp_original.copy()

            loc_terminal_i = np.where(np.asarray(self.labels) == self.terminal_clusters[i])[0]
            # sc_bp[loc_terminal_i,:] = 1.2
            loc_i = np.where(sc_bp[:, i] > 0.8)[0]
            val_pt = [sc_pt[pt_i] for pt_i in loc_i]  # TODO,  replace with array to speed up
            # max_val_pt = np.percentile(np.asarray(val_pt),90)
            max_val_pt = max(val_pt)
            # print('gene exp max pt', max_val_pt)
            loc_i_bp = np.where(sc_bp[:, i] > 0.000)[0]  # 0.001
            loc_i_sc = np.where(np.asarray(sc_pt) <= max_val_pt)[0]
            # print('loc i bp', loc_i_bp)
            # print('loc i sc', loc_i_sc)
            loc_ = np.intersect1d(loc_i_bp, loc_i_sc)
            # print('loc_', loc_.shape)
            gam_in = np.asarray(sc_pt)[loc_]
            x = gam_in.reshape(-1, 1)
            y = np.asarray(gene_exp)[loc_].reshape(-1, 1)
            # print('Gene Expression:', gam_in.shape)
            weights = np.asarray(sc_bp[:, i])[loc_].reshape(-1, 1)

            # print('Gene Expression: setting up subplot number',i)
            if len(loc_) > 1:
                # geneGAM = pg.LinearGAM(n_splines=20, spline_order=5, lam=10).fit(x, y, weights=weights)
                geneGAM = pg.LinearGAM(n_splines=10, spline_order=4, lam=10).fit(x, y, weights=weights)
                nx_spacing = 100
                xval = np.linspace(min(sc_pt), max_val_pt, nx_spacing * 2)
                yg = geneGAM.predict(X=xval)
            else:
                print('loc_ has length zero')

            ax.plot(xval, yg, color=cmap_[i], linewidth=2, zorder=3, linestyle=(0, (5, 2, 1, 2)),
                    dash_capstyle='round', label='TS:' + str(self.terminal_clusters[i]))
        plt.legend()
        plt.title('Gene Expression ' + title_gene)
        return

    def do_magic(self, df_gene, magic_steps=3, gene_list=[]):
        # ad_gene is an ann data object from scanpy
        if self.do_magic_bool == False:
            print(colored('please re-run Via with do_magic set to True', 'red'))
            return
        else:
            from sklearn.preprocessing import normalize
            transition_full_graph = normalize(self.csr_full_graph, norm='l1',
                                              axis=1) ** magic_steps  # normalize across columns to get Transition matrix.
            print('shape of transition matrix raised to power 3', transition_full_graph.shape)
            subset = df_gene[gene_list].values
            print('subset shape', subset.shape)
            dot_ = transition_full_graph.dot(subset)  # np.dot(transition_full_graph,subset )
            print('dot_ product shape', dot_.shape)
            df_imputed_gene = pd.DataFrame(dot_, index=df_gene.index, columns=gene_list)
            print('shape of imputed gene matrix', df_imputed_gene.shape)

            return df_imputed_gene

    def run_subPARC(self):
        root_user = self.root_user
        X_data = self.data
        too_big_factor = self.too_big_factor
        small_pop = self.small_pop
        jac_std_global = self.jac_std_global
        jac_weighted_edges = self.jac_weighted_edges
        n_elements = X_data.shape[0]

        if self.is_coarse == True:
            # graph for PARC
            neighbor_array, distance_array = self.knn_struct.knn_query(X_data, k=self.knn)
            csr_array_locally_pruned = self.make_csrmatrix_noselfloop(neighbor_array,
                                                                      distance_array)  # incorporates  local distance pruning
            sources, targets = csr_array_locally_pruned.nonzero()

            edgelist = list(zip(sources, targets))

            edgelist_copy = edgelist.copy()

            G = ig.Graph(n=X_data.shape[0], edges=edgelist,
                         edge_attrs={'weight': csr_array_locally_pruned.data.tolist()})  # used for PARC
            # print('average degree of prejacard graph is %.1f'% (np.mean(G.degree())))
            # print('computing Jaccard metric')
            sim_list = G.similarity_jaccard(pairs=edgelist_copy)

            print('size neighbor array', neighbor_array.shape)
            print('commencing global pruning')

            sim_list_array = np.asarray(sim_list)
            edge_list_copy_array = np.asarray(edgelist_copy)

            if jac_std_global == 'median':
                threshold = np.median(sim_list)
            else:
                threshold = np.mean(sim_list) - jac_std_global * np.std(sim_list)
            strong_locs = np.where(sim_list_array > threshold)[0]
            print('Share of edges kept after Global Pruning %.2f' % (len(strong_locs) / len(sim_list)), '%')
            new_edgelist = list(edge_list_copy_array[strong_locs])
            sim_list_new = list(sim_list_array[strong_locs])

            G_sim = ig.Graph(n=n_elements, edges=list(new_edgelist), edge_attrs={'weight': sim_list_new})

            G_sim.simplify(combine_edges='sum')

        if self.is_coarse == True:
            #### construct full graph that has no pruning to be used for Clustergraph edges,  # not listed in in any order of proximity
            row_list = []

            n_neighbors = neighbor_array.shape[1]
            n_cells = neighbor_array.shape[0]

            row_list.extend(list(np.transpose(np.ones((n_neighbors, n_cells)) * range(0, n_cells)).flatten()))
            col_list = neighbor_array.flatten().tolist()
            print('distance values', np.percentile(distance_array, 5), np.percentile(distance_array, 95),
                  np.mean(distance_array))
            distance_array = np.sqrt(distance_array)
            weight_list = (1. / (distance_array.flatten() + 0.05))  # 0.05
            mean_sqrt_dist_array = np.mean(distance_array)
            weight_list = weight_list * (mean_sqrt_dist_array ** 2)
            # we scale weight_list by the mean_distance_value because inverting the distances makes the weights range between 0-1
            # and hence too many good neighbors end up having a weight near 0 which is misleading and non-neighbors have weight =0
            weight_list = weight_list.tolist()

            print('distance values', np.percentile(distance_array, 5), np.percentile(distance_array, 95),
                  np.mean(distance_array))
            csr_full_graph = csr_matrix((np.array(weight_list), (np.array(row_list), np.array(col_list))),
                                        shape=(n_cells, n_cells))

            n_original_comp, n_original_comp_labels = connected_components(csr_full_graph, directed=False)
            sources, targets = csr_full_graph.nonzero()
            edgelist = list(zip(sources.tolist(), targets.tolist()))
            G = ig.Graph(edgelist, edge_attrs={'weight': csr_full_graph.data.tolist()})

            sim_list = G.similarity_jaccard(pairs=edgelist)  # list of jaccard weights
            ig_fullgraph = ig.Graph(list(edgelist), edge_attrs={'weight': sim_list})
            ig_fullgraph.simplify(combine_edges='sum')

            self.csr_array_pruned = G_sim  # this graph is pruned for use in PARC
            self.ig_full_graph = ig_fullgraph  # for VIA we prune the vertex cluster graph *after* making the clustergraph
            self.csr_full_graph = csr_full_graph
            self.full_neighbor_array = neighbor_array

        if self.is_coarse == True:
            # knn graph used for making trajectory drawing on the visualization
            self.full_graph_shortpath = self.full_graph_paths(X_data, n_original_comp)
            neighbor_array = self.full_neighbor_array
        if self.is_coarse == False:
            ig_fullgraph = self.ig_full_graph  # for Trajectory
            G_sim = self.csr_array_pruned  # for PARC
            neighbor_array = self.full_neighbor_array  # needed to assign spurious outliers to clusters

        # print('average degree of SIMPLE graph is %.1f' % (np.mean(G_sim.degree())))
        print('commencing community detection')
        if jac_weighted_edges == True:
            start_leiden = time.time()
            # print('call leiden on weighted graph for ', self.n_iter_leiden, 'iterations')
            partition = leidenalg.find_partition(G_sim, leidenalg.ModularityVertexPartition, weights='weight',
                                                 n_iterations=self.n_iter_leiden, seed=self.random_seed)
            print(round(time.time() - start_leiden), ' seconds for leiden')
        else:
            start_leiden = time.time()
            # print('call leiden on unweighted graph', self.n_iter_leiden, 'iterations')
            partition = leidenalg.find_partition(G_sim, leidenalg.ModularityVertexPartition,
                                                 n_iterations=self.n_iter_leiden, seed=self.random_seed)
            print(round(time.time() - start_leiden), ' seconds for leiden')
        time_end_PARC = time.time()
        # print('Q= %.1f' % (partition.quality()))
        PARC_labels_leiden = np.asarray(partition.membership)
        PARC_labels_leiden = np.reshape(PARC_labels_leiden, (n_elements, 1))
        print(len(set(PARC_labels_leiden.flatten())), ' clusters before handling small/big')
        pop_list_1 = []
        count_big_pops = 0
        num_times_expanded = 0
        for item in set(list(PARC_labels_leiden.flatten())):
            count_item = list(PARC_labels_leiden.flatten()).count(item)
            if count_item > self.too_big_factor * n_elements:
                count_big_pops = count_big_pops + 1
            pop_list_1.append([item, count_item])
        print(colored('There are ' + str(count_big_pops) + 'clusters that are too big', 'blue'))
        print(pop_list_1)

        too_big = False

        # print('labels found after Leiden', set(list(PARC_labels_leiden.T)[0])) will have some outlier clusters that need to be added to a cluster if a cluster has members that are KNN

        cluster_i_loc = np.where(PARC_labels_leiden == 0)[
            0]  # the 0th cluster is the largest one. so if cluster 0 is not too big, then the others wont be too big either
        pop_i = len(cluster_i_loc)
        print('largest cluster population', pop_i, too_big_factor, n_elements)
        if pop_i > too_big_factor * n_elements:
            too_big = True
            print('too big is', too_big, ' cluster 0 will be Expanded')

            num_times_expanded = num_times_expanded + 1
            cluster_big_loc = cluster_i_loc
            list_pop_too_bigs = [pop_i]
            cluster_too_big = 0
        time0_big = time.time()
        # while (too_big == True)&(time.time()-time0_big<600):
        while (too_big == True) & (not ((time.time() - time0_big > 200) & (num_times_expanded >= count_big_pops))):
            X_data_big = X_data[cluster_big_loc, :]
            print(X_data_big.shape)
            PARC_labels_leiden_big = self.run_toobig_subPARC(X_data_big)
            num_times_expanded = num_times_expanded + 1
            # print('set of new big labels ', set(PARC_labels_leiden_big.flatten()))
            PARC_labels_leiden_big = PARC_labels_leiden_big + 100000
            # print('set of new big labels +1000 ', set(list(PARC_labels_leiden_big.flatten())))
            pop_list = []
            for item in set(list(PARC_labels_leiden_big.flatten())):
                pop_list.append([item, list(PARC_labels_leiden_big.flatten()).count(item)])

            print('pop of new big labels', pop_list)
            jj = 0
            print('shape PARC_labels_leiden', PARC_labels_leiden.shape)
            for j in cluster_big_loc:
                PARC_labels_leiden[j] = PARC_labels_leiden_big[jj]
                jj = jj + 1
            dummy, PARC_labels_leiden = np.unique(list(PARC_labels_leiden.flatten()), return_inverse=True)
            # print('new set of labels ')
            pop_list_1 = []
            for item in set(list(PARC_labels_leiden.flatten())):
                pop_list_1.append([item, list(PARC_labels_leiden.flatten()).count(item)])
            print(pop_list_1, set(PARC_labels_leiden))
            too_big = False
            set_PARC_labels_leiden = set(PARC_labels_leiden)
            print('set PARC labels leiden', set_PARC_labels_leiden)
            PARC_labels_leiden = np.asarray(PARC_labels_leiden)
            for cluster_ii in set_PARC_labels_leiden:
                cluster_ii_loc = np.where(PARC_labels_leiden == cluster_ii)[0]
                pop_ii = len(cluster_ii_loc)
                not_yet_expanded = pop_ii not in list_pop_too_bigs
                if (pop_ii > too_big_factor * n_elements) & (not_yet_expanded) == True:
                    too_big = True
                    # print('cluster', cluster_ii, 'is too big and has population', pop_ii)
                    cluster_big_loc = cluster_ii_loc
                    cluster_big = cluster_ii
                    big_pop = pop_ii
            if too_big == True:
                list_pop_too_bigs.append(big_pop)
                print('cluster', cluster_big, 'is too big with population', big_pop, '. It will be expanded')
        dummy, PARC_labels_leiden = np.unique(list(PARC_labels_leiden.flatten()), return_inverse=True)
        small_pop_list = []
        small_cluster_list = []
        small_pop_exist = False

        for cluster in set(PARC_labels_leiden):
            population = len(np.where(PARC_labels_leiden == cluster)[0])

            if population < small_pop:  # 10
                small_pop_exist = True

                small_pop_list.append(list(np.where(PARC_labels_leiden == cluster)[0]))
                small_cluster_list.append(cluster)

        for small_cluster in small_pop_list:

            for single_cell in small_cluster:
                old_neighbors = neighbor_array[single_cell, :]
                group_of_old_neighbors = PARC_labels_leiden[old_neighbors]
                group_of_old_neighbors = list(group_of_old_neighbors.flatten())
                available_neighbours = set(group_of_old_neighbors) - set(small_cluster_list)
                if len(available_neighbours) > 0:
                    available_neighbours_list = [value for value in group_of_old_neighbors if
                                                 value in list(available_neighbours)]
                    best_group = max(available_neighbours_list, key=available_neighbours_list.count)
                    PARC_labels_leiden[single_cell] = best_group
        time_smallpop = time.time()
        while (small_pop_exist) == True & (time.time() - time_smallpop < 15):
            small_pop_list = []
            small_pop_exist = False
            for cluster in set(list(PARC_labels_leiden.flatten())):
                population = len(np.where(PARC_labels_leiden == cluster)[0])
                if population < small_pop:
                    small_pop_exist = True
                    # print(cluster, ' has small population of', population, )
                    small_pop_list.append(np.where(PARC_labels_leiden == cluster)[0])
            for small_cluster in small_pop_list:
                for single_cell in small_cluster:
                    old_neighbors = neighbor_array[single_cell, :]
                    group_of_old_neighbors = PARC_labels_leiden[old_neighbors]
                    group_of_old_neighbors = list(group_of_old_neighbors.flatten())
                    best_group = max(set(group_of_old_neighbors), key=group_of_old_neighbors.count)
                    PARC_labels_leiden[single_cell] = best_group

        dummy, PARC_labels_leiden = np.unique(list(PARC_labels_leiden.flatten()), return_inverse=True)
        PARC_labels_leiden = list(PARC_labels_leiden.flatten())
        # print('final labels allocation', set(PARC_labels_leiden))
        pop_list = []
        pop_list_raw = []
        for item in range(len(set(PARC_labels_leiden))):
            pop_item = PARC_labels_leiden.count(item)
            pop_list.append((item, pop_item))
            pop_list_raw.append(pop_item)
        print('list of cluster labels and populations', len(pop_list), pop_list)

        self.labels = PARC_labels_leiden  # list
        n_clus = len(set(self.labels))

        ##determine majority truth

        if self.pseudotime == True:

            ## Make cluster-graph (1)

            vc_graph = ig.VertexClustering(ig_fullgraph,
                                           membership=PARC_labels_leiden)  # jaccard weights, bigger is better

            vc_graph = vc_graph.cluster_graph(combine_edges='sum')

            # print('vc graph G_sim', vc_graph)
            # print('vc graph G_sim old', vc_graph_old)

            reweighted_sparse_vc, edgelist = self.recompute_weights(vc_graph, pop_list_raw)

            print('len old edge list', edgelist)  # 0.15 for CD34
            if self.dataset == 'toy':  # ''humanCD34':# == False:
                global_pruning_std = 0.5  # 2
                print('Toy: global cluster graph pruning level', global_pruning_std)
            # toy data is usually simpler so we dont need to prune the links as the clusters are usually well separated such that spurious links dont exist
            elif self.dataset == 'bcell':
                global_pruning_std = 0.15
                print('Bcell: global cluster graph pruning level', global_pruning_std)
            elif self.dataset == 'iPSC':
                global_pruning_std = 0.15
                print('iPSC: global cluster graph pruning level', global_pruning_std)
            elif self.dataset == 'EB':
                global_pruning_std = 0.15
                print('EB: global cluster graph pruning level', global_pruning_std)

            elif self.dataset == 'mESC':
                global_pruning_std = 0.0
                print('mESC: global cluster graph pruning level', global_pruning_std)
            else:
                global_pruning_std = 0.15
                print('Humancd34: global cluster graph pruning level', global_pruning_std)
            edgeweights, edgelist, comp_labels = local_pruning_clustergraph_mst(reweighted_sparse_vc,
                                                                                global_pruning_std=global_pruning_std,
                                                                                preserve_disconnected=self.preserve_disconnected)  # 0.8 on 20knn and 40ncomp #0.15
            self.connected_comp_labels = comp_labels
            print('final comp labels set', set(comp_labels))

            print('len new edge list', edgelist)

            locallytrimmed_g = ig.Graph(edgelist, edge_attrs={'weight': edgeweights.tolist()})
            # print('locally trimmed_g', locallytrimmed_g)
            locallytrimmed_g = locallytrimmed_g.simplify(combine_edges='sum')
            # print('locally trimmed and simplified', locallytrimmed_g)

            locallytrimmed_sparse_vc = get_sparse_from_igraph(locallytrimmed_g, weight_attr='weight')
            layout = locallytrimmed_g.layout_fruchterman_reingold(
                weights='weight')  ##final layout based on locally trimmed

            # globally trimmed link
            sources, targets = locallytrimmed_sparse_vc.nonzero()
            edgelist_simple = list(zip(sources.tolist(), targets.tolist()))
            edgelist_unique = set(tuple(sorted(l)) for l in edgelist_simple)  # keep only one of (0,1) and (1,0)
            self.edgelist_unique = edgelist_unique
            print('edge list unique', edgelist_unique)
            self.edgelist = edgelist

            x_lazy = self.x_lazy
            alpha_teleport = self.alpha_teleport

            # number of components
            graph_dict = {}
            n_components, labels = connected_components(csgraph=locallytrimmed_sparse_vc, directed=False,
                                                        return_labels=True)
            print('there are ', n_components, 'components in the graph')
            df_graph = pd.DataFrame(locallytrimmed_sparse_vc.todense())
            df_graph['cc'] = labels
            df_graph['pt'] = float('NaN')
            df_graph['markov_pt'] = float('NaN')
            df_graph['majority_truth'] = 'maj truth'
            df_graph['graph_node_label'] = 'node label'
            set_parc_labels = list(set(PARC_labels_leiden))
            set_parc_labels.sort()
            print('parc labels', set_parc_labels)
            # for ii, jj in enumerate(PARC_labels_leiden):

            terminal_clus = []
            node_deg_list = []
            super_terminal_clus_revised = []
            pd_columnnames_terminal = []
            dict_terminal_super_sub_pairs = {}
            self.root = []
            for comp_i in range(n_components):
                loc_compi = np.where(labels == comp_i)[0]

                a_i = df_graph.iloc[loc_compi][loc_compi].values
                a_i = csr_matrix(a_i, (a_i.shape[0], a_i.shape[0]))
                cluster_labels_subi = [x for x in loc_compi]
                print('cluster_labels_subi', cluster_labels_subi)
                sc_labels_subi = [PARC_labels_leiden[i] for i in range(len(PARC_labels_leiden)) if
                                  (PARC_labels_leiden[i] in cluster_labels_subi)]
                sc_truelabels_subi = [self.true_label[i] for i in range(len(PARC_labels_leiden)) if
                                      (PARC_labels_leiden[i] in cluster_labels_subi)]

                if (self.dataset == 'toy'):
                    print('made it ')
                    if self.super_cluster_labels != False:

                        if 'T1_M1' in sc_truelabels_subi:
                            root_user = 'T1_M1'
                        elif 'T2_M1' in sc_truelabels_subi:
                            root_user = 'T2_M1'
                        super_labels_subi = [self.super_cluster_labels[i] for i in range(len(PARC_labels_leiden)) if
                                             (PARC_labels_leiden[i] in cluster_labels_subi)]
                        print('super node degree', self.super_node_degree_list)
                        print('component', comp_i, 'has root', root_user[comp_i])
                        print('super_labels_subi', super_labels_subi)

                        graph_node_label, majority_truth_labels, node_deg_list_i, root_i = self.find_root(a_i,
                                                                                                          sc_labels_subi,
                                                                                                          root_user,
                                                                                                          sc_truelabels_subi,
                                                                                                          super_labels_subi,
                                                                                                          self.super_node_degree_list)
                    else:
                        if 'T1_M1' in sc_truelabels_subi:
                            root_user = 'T1_M1'
                        elif 'T2_M1' in sc_truelabels_subi:
                            root_user = 'T2_M1'
                        print('component', comp_i, 'has root', root_user[comp_i])
                        graph_node_label, majority_truth_labels, node_deg_list_i, root_i = self.find_root(a_i,
                                                                                                          sc_labels_subi,
                                                                                                          root_user,
                                                                                                          sc_truelabels_subi,
                                                                                                          [], [])

                elif self.dataset == 'humanCD34':
                    graph_node_label, majority_truth_labels, node_deg_list_i, root_i = self.find_root_HumanCD34(a_i,
                                                                                                                sc_labels_subi,
                                                                                                                root_user,
                                                                                                                sc_truelabels_subi)
                elif (self.dataset == 'bcell') | (self.dataset == 'EB'):
                    '''
                    if self.super_cluster_labels != False:
                        super_labels_subi = [self.super_cluster_labels[i] for i in range(len(PARC_labels_leiden)) if
                                             (PARC_labels_leiden[i] in cluster_labels_subi)]
                        graph_node_label, majority_truth_labels, node_deg_list_i, root_i = self.find_root(a_i,
                                                                                                          sc_labels_subi,
                                                                                                          root_user,
                                                                                                          sc_truelabels_subi,
                                                                                                          super_labels_subi,
                                                                                                          self.super_node_degree_list)

                    else:  # if this is p0.run()

                    graph_node_label, majority_truth_labels, node_deg_list_i, root_i = self.find_root(a_i,
                                                                                                      sc_labels_subi,
                                                                                                      root_user,
                                                                                                      sc_truelabels_subi,
                                                                                                      [], [])

                    '''
                    graph_node_label, majority_truth_labels, node_deg_list_i, root_i = self.find_root_bcell(a_i,
                                                                                                            sc_labels_subi,
                                                                                                            root_user,
                                                                                                            sc_truelabels_subi)
                elif ((self.dataset == 'iPSC') | (self.dataset == 'mESC')):
                    print('in iPSC root')
                    if self.super_cluster_labels != False:
                        super_labels_subi = [self.super_cluster_labels[i] for i in range(len(PARC_labels_leiden)) if
                                             (PARC_labels_leiden[i] in cluster_labels_subi)]
                        print('super node degree', self.super_node_degree_list)

                        graph_node_label, majority_truth_labels, node_deg_list_i, root_i = self.find_root_iPSC(a_i,
                                                                                                               sc_labels_subi,
                                                                                                               root_user,
                                                                                                               sc_truelabels_subi,
                                                                                                               super_labels_subi,
                                                                                                               self.super_node_degree_list)
                    else:
                        graph_node_label, majority_truth_labels, node_deg_list_i, root_i = self.find_root_iPSC(a_i,
                                                                                                               sc_labels_subi,
                                                                                                               root_user,
                                                                                                               sc_truelabels_subi,
                                                                                                               [], [])

                self.root.append(root_i)
                for item in node_deg_list_i:
                    node_deg_list.append(item)
                print('a_i shape, true labels shape', a_i.shape, len(sc_truelabels_subi), len(sc_labels_subi))

                new_root_index_found = False
                for ii, llabel in enumerate(cluster_labels_subi):
                    if root_i == llabel:
                        new_root_index = ii
                        new_root_index_found = True
                        print('new root index', new_root_index, ' original root cluster was', root_i)
                if new_root_index_found == False:
                    print('cannot find the new root index')
                    new_root_index = 0
                hitting_times, roundtrip_times = self.compute_hitting_time(a_i, root=new_root_index,
                                                                           x_lazy=x_lazy, alpha_teleport=alpha_teleport)
                # rescale hitting times
                very_high = np.mean(hitting_times) + 1.5 * np.std(hitting_times)
                without_very_high_pt = [iii for iii in hitting_times if iii < very_high]
                new_very_high = np.mean(without_very_high_pt) + np.std(without_very_high_pt)
                print('very high, and new very high', very_high, new_very_high)
                new_hitting_times = [x if x < very_high else very_high for x in hitting_times]
                hitting_times = np.asarray(new_hitting_times)
                scaling_fac = 10 / max(hitting_times)
                hitting_times = hitting_times * scaling_fac
                s_ai, t_ai = a_i.nonzero()
                edgelist_ai = list(zip(s_ai, t_ai))
                edgeweights_ai = a_i.data
                # print('edgelist ai', edgelist_ai)
                # print('edgeweight ai', edgeweights_ai)
                biased_edgeweights_ai = get_biased_weights(edgelist_ai, edgeweights_ai, hitting_times)

                # biased_sparse = csr_matrix((biased_edgeweights, (row, col)))
                adjacency_matrix_ai = np.zeros((a_i.shape[0], a_i.shape[0]))

                for i, (start, end) in enumerate(edgelist_ai):
                    adjacency_matrix_ai[start, end] = biased_edgeweights_ai[i]

                markov_hitting_times_ai = self.simulate_markov(adjacency_matrix_ai,
                                                               new_root_index)  # +adjacency_matrix.T))
                print('markov_hitting times ')
                # for eee, ttt in enumerate(markov_hitting_times_ai):print('cluster ', eee, ' had markov time', ttt)

                very_high = np.mean(markov_hitting_times_ai) + 1.5 * np.std(markov_hitting_times_ai)  # 1.5
                very_high = min(very_high, max(markov_hitting_times_ai))
                without_very_high_pt = [iii for iii in markov_hitting_times_ai if iii < very_high]
                new_very_high = min(np.mean(without_very_high_pt) + np.std(without_very_high_pt), very_high)
                print('very high, and new very high', very_high, new_very_high)
                new_markov_hitting_times_ai = [x if x < very_high else very_high for x in markov_hitting_times_ai]
                # for eee, ttt in enumerate(new_markov_hitting_times_ai):      print('cluster ', eee, ' had markov time', ttt)

                markov_hitting_times_ai = np.asarray(new_markov_hitting_times_ai)
                scaling_fac = 10 / max(markov_hitting_times_ai)
                markov_hitting_times_ai = markov_hitting_times_ai * scaling_fac
                # for eee, ttt in enumerate(markov_hitting_times_ai):print('cluster ', eee, ' had markov time', ttt)

                # print('markov hitting times', [(i, j) for i, j in enumerate(markov_hitting_times_ai)])
                # print('hitting times', [(i, j) for i, j in enumerate(hitting_times)])
                markov_hitting_times_ai = (markov_hitting_times_ai)  # + hitting_times)*.5 #consensus
                adjacency_matrix_csr_ai = sparse.csr_matrix(adjacency_matrix_ai)
                (sources, targets) = adjacency_matrix_csr_ai.nonzero()
                edgelist_ai = list(zip(sources, targets))
                weights_ai = adjacency_matrix_csr_ai.data
                bias_weights_2_ai = get_biased_weights(edgelist_ai, weights_ai, markov_hitting_times_ai, round_no=2)
                adjacency_matrix2_ai = np.zeros((adjacency_matrix_ai.shape[0], adjacency_matrix_ai.shape[0]))

                for i, (start, end) in enumerate(edgelist_ai):
                    adjacency_matrix2_ai[start, end] = bias_weights_2_ai[i]
                if self.super_terminal_cells == False:
                    print('new_root_index', new_root_index, ' before get terminal')
                    terminal_clus_ai = self.get_terminal_clusters(adjacency_matrix2_ai, markov_hitting_times_ai,
                                                                  new_root_index)
                    for i in terminal_clus_ai:
                        terminal_clus.append(cluster_labels_subi[i])


                elif len(self.super_terminal_clusters) > 0:  # round2 of PARC
                    print('super_terminal_clusters', self.super_terminal_clusters)
                    sub_terminal_clus_temp_ = []
                    print('cluster_labels_subi', cluster_labels_subi)
                    terminal_clus_ai = []
                    super_terminal_clusters_i = [stc_i for stc_i in self.super_terminal_clusters if
                                                 stc_i in cluster_labels_subi]
                    print('super_terminal_clusters_i', super_terminal_clusters_i)
                    for i in self.super_terminal_clusters:
                        print('super cluster terminal label', i)
                        sub_terminal_clus_temp_loc = np.where(np.asarray(self.super_cluster_labels) == i)[0]
                        true_majority_i = [xx for xx in self.true_label[sub_terminal_clus_temp_loc]]
                        print(true_majority_i[0], 'true_majority_i', 'of cluster', i)
                        if root_user[0:1] in true_majority_i[0]:  # 0:2

                            print('sub_terminal_clus_temp_loc', sub_terminal_clus_temp_loc)
                            temp_set = set(list(np.asarray(self.labels)[sub_terminal_clus_temp_loc]))
                            print('first temp_set of TS', temp_set)
                            temp_set = [t_s for t_s in temp_set if t_s in cluster_labels_subi]
                            # print('loc compi', loc_compi)
                            # temp_set = []
                            # for temp_set_i in temp_set_0:
                            #    temp_set_ii = np.where(loc_compi==temp_set_i)[0]
                            #    temp_set.append(temp_set_ii)

                            print('second temp_set of TS', temp_set)
                            # print('temp set', temp_set)
                            temp_max_pt = 0
                            most_likely_sub_terminal = False
                            count_frequency_super_in_sub = 0
                            for j in temp_set:
                                loc_j_in_sub_ai = np.where(loc_compi == j)[0]
                                print('loc_j_in_sub_ai', loc_j_in_sub_ai)
                                super_cluster_composition_loc = np.where(np.asarray(self.labels) == j)[0]
                                super_cluster_composition = self.func_mode(
                                    list(np.asarray(self.super_cluster_labels)[super_cluster_composition_loc]))
                                print('the composition of sub cluster', j, 'is mostly', super_cluster_composition)
                                if (markov_hitting_times_ai[loc_j_in_sub_ai] > temp_max_pt) & (
                                        super_cluster_composition == i):
                                    temp_max_pt = markov_hitting_times_ai[loc_j_in_sub_ai]
                                    print('super, j and temp max pt', i, j, temp_max_pt)
                                    most_likely_sub_terminal = j
                            if most_likely_sub_terminal == False:
                                print('no sub cluster has majority made of super-cluster ', i)
                                for j in temp_set:
                                    super_cluster_composition_loc = np.where(np.asarray(self.labels) == j)[0]
                                    count_frequency_super_in_sub_temp = list(
                                        np.asarray(self.super_cluster_labels)[super_cluster_composition_loc]).count(i)
                                    count_frequency_super_in_sub_temp_ratio = count_frequency_super_in_sub_temp / len(
                                        super_cluster_composition_loc)
                                    if (markov_hitting_times_ai[loc_j_in_sub_ai] > np.percentile(
                                            np.asarray(markov_hitting_times_ai), 30)) & (  # 30
                                            count_frequency_super_in_sub_temp_ratio > count_frequency_super_in_sub):
                                        count_frequency_super_in_sub = count_frequency_super_in_sub_temp
                                        # temp_max_pt = markov_hitting_times_ai[j]
                                        most_likely_sub_terminal = j

                            sub_terminal_clus_temp_.append(most_likely_sub_terminal)

                            if (markov_hitting_times_ai[loc_j_in_sub_ai] > np.percentile(
                                    np.asarray(markov_hitting_times_ai), 30)):  # 30

                                dict_terminal_super_sub_pairs.update({i: most_likely_sub_terminal})
                                super_terminal_clus_revised.append(i)
                                terminal_clus.append(most_likely_sub_terminal)
                                terminal_clus_ai.append(
                                    np.where(np.asarray(cluster_labels_subi) == most_likely_sub_terminal)[0][0])  # =i
                                # terminal_clus_ai.append(most_likely_sub_terminal)
                                print('the sub terminal cluster that best captures the super terminal', i, 'is',
                                      most_likely_sub_terminal)
                            else:
                                print('the sub terminal cluster that best captures the super terminal', i, 'is',
                                      most_likely_sub_terminal, 'but the pseudotime is too low')


                else:
                    print('super terminal cells', self.super_terminal_cells)

                    print([self.labels[ti] for ti in
                           self.super_terminal_cells])  # find the sub-cluster which contains the single-cell-superterminal
                    temp = [self.labels[ti] for ti in self.super_terminal_cells if
                            self.labels[ti] in cluster_labels_subi]
                    terminal_clus_ai = []
                    for i in temp:
                        terminal_clus_ai.append(np.where(np.asarray(cluster_labels_subi) == i)[0][0])
                        terminal_clus.append(i)
                        dict_terminal_super_sub_pairs.update({i: most_likely_sub_terminal})

                    # for i in temp:
                    #    terminal_clus.append(i)
                print('terminal clus in this a_i', terminal_clus_ai)
                print('final terminal clus', terminal_clus)
                for target_terminal in terminal_clus_ai:

                    # prob_ai = self.prob_reaching_terminal_state(target_terminal, terminal_clus_ai, adjacency_matrix2_ai,  new_root_index, pt=markov_hitting_times_ai,  num_sim=500)
                    prob_ai = self.simulate_branch_probability(target_terminal, terminal_clus_ai, adjacency_matrix2_ai,
                                                               new_root_index, pt=markov_hitting_times_ai,
                                                               num_sim=50)  # 50 ToDO change back to 500 = numsim
                    df_graph['terminal_clus' + str(cluster_labels_subi[target_terminal])] = 0.0000000

                    pd_columnnames_terminal.append('terminal_clus' + str(cluster_labels_subi[target_terminal]))

                    print('prob ai for target terminal', target_terminal, prob_ai)
                    for k, prob_ii in enumerate(prob_ai):
                        df_graph.at[cluster_labels_subi[k], 'terminal_clus' + str(
                            cluster_labels_subi[target_terminal])] = prob_ii
                bp_array = df_graph[pd_columnnames_terminal].values
                bp_array[np.isnan(bp_array)] = 0.00000001
                # print('final bp_array NOT normed by rowsum', bp_array)
                bp_array = bp_array / bp_array.sum(axis=1)[:, None]
                bp_array[np.isnan(bp_array)] = 0.00000001
                # print('final bp_array normed by rowsum', bp_array)

                for ei, ii in enumerate(loc_compi):
                    df_graph.at[ii, 'pt'] = hitting_times[ei]
                    df_graph.at[ii, 'graph_node_label'] = graph_node_label[ei]

                    df_graph.at[ii, 'majority_truth'] = graph_node_label[ei]

                    df_graph.at[ii, 'markov_pt'] = markov_hitting_times_ai[ei]

            locallytrimmed_g.vs["label"] = df_graph['graph_node_label'].values

            hitting_times = df_graph['pt'].values

            if len(super_terminal_clus_revised) > 0:
                self.revised_super_terminal_clusters = super_terminal_clus_revised
            else:
                self.revised_super_terminal_clusters = self.super_terminal_clusters
            self.hitting_times = hitting_times  # * 1000
            self.markov_hitting_times = df_graph['markov_pt'].values  # hitting_times#
            self.terminal_clusters = terminal_clus
            print('terminal clusters', terminal_clus)
            self.node_degree_list = node_deg_list
            print(colored('project onto sc', 'red'))

            self.project_branch_probability_sc(bp_array, df_graph['markov_pt'].values)
            self.dict_terminal_super_sub_pairs = dict_terminal_super_sub_pairs
            hitting_times = self.markov_hitting_times

            bias_weights_2_all = get_biased_weights(edgelist, edgeweights, self.markov_hitting_times, round_no=2)
            row_list = []
            col_list = []
            for (rowi, coli) in edgelist:
                row_list.append(rowi)
                col_list.append(coli)
            # print('shape', a_i.shape[0], a_i.shape[0], row_list)
            temp_csr = csr_matrix((np.array(bias_weights_2_all), (np.array(row_list), np.array(col_list))),
                                  shape=(n_clus, n_clus))
            if self.dataset == 'toy':  # 'humanCD34':#False:
                visual_global_pruning_std = 0.15
                max_outgoing = 2  # 4
            else:
                visual_global_pruning_std = 1  # 0.15#0 for human
                max_outgoing = 2
            # glob_std_pruning =0 and max_out = 2 for HumanCD34 to simplify structure
            edgeweights_maxout_2, edgelist_maxout_2, comp_labels_2 = local_pruning_clustergraph_mst(temp_csr,
                                                                                                    global_pruning_std=visual_global_pruning_std,
                                                                                                    max_outgoing=max_outgoing,
                                                                                                    preserve_disconnected=self.preserve_disconnected)

            row_list = []
            col_list = []
            for (rowi, coli) in edgelist_maxout_2:
                row_list.append(rowi)
                col_list.append(coli)
            temp_csr = csr_matrix((np.array(edgeweights_maxout_2), (np.array(row_list), np.array(col_list))),
                                  shape=(n_clus, n_clus))
            temp_csr = temp_csr.transpose().todense() + temp_csr.todense()
            temp_csr = np.tril(temp_csr, -1)  # elements along the main diagonal and above are set to zero
            temp_csr = csr_matrix(temp_csr)
            edgeweights_maxout_2 = temp_csr.data
            scale_factor = max(edgeweights_maxout_2) - min(edgeweights_maxout_2)
            edgeweights_maxout_2 = [((wi + .1) * 2.5 / scale_factor) + 0.1 for wi in edgeweights_maxout_2]

            sources, targets = temp_csr.nonzero()
            edgelist_maxout_2 = list(zip(sources.tolist(), targets.tolist()))
            self.edgelist_maxout = edgelist_maxout_2
            self.edgeweights_maxout = edgeweights_maxout_2

            remove_outliers = hitting_times

            threshold = np.percentile(remove_outliers, 95)  # np.mean(remove_outliers) + 1* np.std(remove_outliers)

            th_hitting_times = [x if x < threshold else threshold for x in hitting_times]

            remove_outliers_low = hitting_times[hitting_times < (np.mean(hitting_times) - 0.3 * np.std(hitting_times))]
            threshold_low = np.mean(remove_outliers_low) - 0.3 * np.std(remove_outliers_low)
            threshold_low = np.percentile(remove_outliers_low, 5)
            # print('thresh low', threshold_low)
            th_hitting_times = [x if x > threshold_low else threshold_low for x in th_hitting_times]

            scaled_hitting_times = (th_hitting_times - np.min(th_hitting_times))
            scaled_hitting_times = scaled_hitting_times * (1000 / np.max(scaled_hitting_times))

            self.scaled_hitting_times = scaled_hitting_times
            # self.single_cell_pt = self.project_hittingtimes_sc(self.hitting_times)
            # self.single_cell_pt_stationary_bias = self.project_hittingtimes_sc(self.stationary_hitting_times.flatten())
            # self.dijkstra_hitting_times = self.path_length_onbias(edgelist, biased_edgeweights)
            # print('dijkstra hitting times', [(i,j) for i,j in enumerate(self.dijkstra_hitting_times)])
            # self.single_cell_pt_dijkstra_bias = self.project_hittingtimes_sc(self.dijkstra_hitting_times)

            scaled_hitting_times = scaled_hitting_times.astype(int)

            pal = ig.drawing.colors.AdvancedGradientPalette(['yellow', 'green', 'blue'], n=1001)

            all_colors = []

            for i in scaled_hitting_times:
                all_colors.append(pal.get(int(i))[0:3])

            locallytrimmed_g.vs['hitting_times'] = scaled_hitting_times

            locallytrimmed_g.vs['color'] = [pal.get(i)[0:3] for i in scaled_hitting_times]

            self.group_color = [colors.to_hex(v) for v in locallytrimmed_g.vs['color']]  # based on ygb scale
            viridis_cmap = cm.get_cmap('viridis_r')

            self.group_color_cmap = [colors.to_hex(v) for v in
                                     viridis_cmap(scaled_hitting_times / 1000)]  # based on ygb scale

        self.graph_node_label = df_graph['graph_node_label'].values
        self.edgeweight = [e['weight'] * 1 for e in locallytrimmed_g.es]
        print('self edge weight', len(self.edgeweight), self.edgeweight)
        print('self edge list', len(self.edgelist_unique), self.edgelist_unique)
        self.graph_node_pos = layout.coords
        f, ((ax, ax1)) = plt.subplots(1, 2, sharey=True)

        self.draw_piechart_graph(ax, ax1)

        plt.show()
        return

    def draw_piechart_graph(self, ax, ax1, type_pt='original', ):

        arrow_head_w = 0.4  # 0.2
        edgeweight_scale = 1

        node_pos = self.graph_node_pos
        edgelist = list(self.edgelist_maxout)
        edgeweight = self.edgeweights_maxout

        node_pos = np.asarray(node_pos)

        graph_node_label = self.graph_node_label
        if type_pt == 'original': pt = self.scaled_hitting_times
        if type_pt == 'biased_stationary': pt = self.biased_hitting_times_stationary
        if type_pt == 'markov': pt = self.markov_hitting_times
        import matplotlib.lines as lines

        n_groups = len(set(self.labels))  # node_pos.shape[0]
        n_truegroups = len(set(self.true_label))
        group_pop = np.zeros([n_groups, 1])
        group_frac = pd.DataFrame(np.zeros([n_groups, n_truegroups]), columns=list(set(self.true_label)))

        for group_i in set(self.labels):
            loc_i = np.where(self.labels == group_i)[0]

            group_pop[group_i] = len(loc_i)  # np.sum(loc_i) / 1000 + 1
            true_label_in_group_i = list(np.asarray(self.true_label)[[loc_i]])
            for ii in set(true_label_in_group_i):
                group_frac[ii][group_i] = true_label_in_group_i.count(ii)
        group_frac = group_frac.div(group_frac.sum(axis=1), axis=0)

        line_true = np.linspace(0, 1, n_truegroups)
        color_true_list = [plt.cm.jet(color) for color in line_true]

        sct = ax.scatter(
            node_pos[:, 0], node_pos[:, 1],
            c='white', edgecolors='face', s=group_pop, cmap='jet')
        print('draw triangle edgelist', len(edgelist), edgelist)
        for e_i, (start, end) in enumerate(edgelist):
            if pt[start] > pt[end]:
                temp = start
                start = end
                end = temp

            ax.add_line(lines.Line2D([node_pos[start, 0], node_pos[end, 0]], [node_pos[start, 1], node_pos[end, 1]],
                                     color='grey', lw=edgeweight[e_i] * edgeweight_scale, alpha=0.2))
            z = np.polyfit([node_pos[start, 0], node_pos[end, 0]], [node_pos[start, 1], node_pos[end, 1]], 1)
            minx = np.min(np.array([node_pos[start, 0], node_pos[end, 0]]))

            if (node_pos[start, 0] < node_pos[end, 0]):
                direction_arrow = 1
            else:
                direction_arrow = -1

            maxx = np.max(np.array([node_pos[start, 0], node_pos[end, 0]]))

            xp = np.linspace(minx, maxx, 500)
            p = np.poly1d(z)
            smooth = p(xp)
            step = 1
            if direction_arrow == 1:

                ax.arrow(xp[250], smooth[250], xp[250 + step] - xp[250], smooth[250 + step] - smooth[250], shape='full',
                         lw=0,
                         length_includes_head=True, head_width=arrow_head_w,
                         color='grey')
                # ax.plot(xp, smooth, linewidth=edgeweight[e_i], c='pink')
            else:
                ax.arrow(xp[250], smooth[250], xp[250 - step] - xp[250],
                         smooth[250 - step] - smooth[250], shape='full', lw=0,
                         length_includes_head=True, head_width=arrow_head_w, color='grey')
        trans = ax.transData.transform
        bbox = ax.get_position().get_points()
        ax_x_min = bbox[0, 0]
        ax_x_max = bbox[1, 0]
        ax_y_min = bbox[0, 1]
        ax_y_max = bbox[1, 1]
        ax_len_x = ax_x_max - ax_x_min
        ax_len_y = ax_y_max - ax_y_min
        trans2 = ax.transAxes.inverted().transform
        pie_axs = []
        pie_size_ar = ((group_pop - np.min(group_pop)) / (np.max(group_pop) - np.min(group_pop)) + 0.5) / 10

        for node_i in range(n_groups):
            pie_size = pie_size_ar[node_i][0]

            x1, y1 = trans(node_pos[node_i])  # data coordinates

            xa, ya = trans2((x1, y1))  # axis coordinates

            xa = ax_x_min + (xa - pie_size / 2) * ax_len_x
            ya = ax_y_min + (ya - pie_size / 2) * ax_len_y
            # clip, the fruchterman layout sometimes places below figure
            # if ya < 0: ya = 0
            # if xa < 0: xa = 0
            rect = [xa, ya, pie_size * ax_len_x, pie_size * ax_len_y]
            frac = group_frac.iloc[node_i].values
            pie_axs.append(plt.axes(rect, frameon=False))
            pie_axs[node_i].pie(frac, wedgeprops={'linewidth': 0.0}, colors=color_true_list)
            pie_axs[node_i].set_xticks([])
            pie_axs[node_i].set_yticks([])
            pie_axs[node_i].set_aspect('equal')
            pie_axs[node_i].text(0.5, 0.5, graph_node_label[node_i])

        patches, texts = pie_axs[node_i].pie(frac, wedgeprops={'linewidth': 0.0}, colors=color_true_list)
        labels = list(set(self.true_label))
        plt.legend(patches, labels, loc=(-5, -5), fontsize=6)
        if self.too_big_factor >= 0.1:
            is_sub = ' super clusters'
        else:
            is_sub = ' sub clusters'
        ti = 'Reference Group Membership. K=' + str(self.knn) + '. ncomp = ' + str(self.ncomp) + is_sub
        ax.set_title(ti)

        title_list = ["PT using Markov Simulation"]  # , "PT on undirected original graph"]
        for i, ax_i in enumerate([ax1]):
            print("drawing axis", i)
            if i == 0:  pt = self.markov_hitting_times
            if i == 1: pt = self.hitting_times

            for e_i, (start, end) in enumerate(edgelist):
                if pt[start] > pt[end]:
                    temp = start
                    start = end
                    end = temp

                ax_i.add_line(
                    lines.Line2D([node_pos[start, 0], node_pos[end, 0]], [node_pos[start, 1], node_pos[end, 1]],
                                 color='black', lw=edgeweight[e_i] * edgeweight_scale, alpha=0.5))
                z = np.polyfit([node_pos[start, 0], node_pos[end, 0]], [node_pos[start, 1], node_pos[end, 1]], 1)
                minx = np.min(np.array([node_pos[start, 0], node_pos[end, 0]]))

                if (node_pos[start, 0] < node_pos[end, 0]):
                    direction_arrow = 1
                else:
                    direction_arrow = -1

                maxx = np.max(np.array([node_pos[start, 0], node_pos[end, 0]]))

                xp = np.linspace(minx, maxx, 500)
                p = np.poly1d(z)
                smooth = p(xp)
                step = 1
                if direction_arrow == 1:

                    ax_i.arrow(xp[250], smooth[250], xp[250 + step] - xp[250], smooth[250 + step] - smooth[250],
                               shape='full', lw=0,
                               length_includes_head=True, head_width=arrow_head_w,
                               color='grey')

                else:
                    ax_i.arrow(xp[250], smooth[250], xp[250 - step] - xp[250],
                               smooth[250 - step] - smooth[250], shape='full', lw=0,
                               length_includes_head=True, head_width=arrow_head_w, color='grey')
            c_edge = []
            l_width = []
            for ei, pti in enumerate(pt):
                if ei in self.terminal_clusters:
                    c_edge.append('red')
                    l_width.append(1.5)
                else:
                    c_edge.append('gray')
                    l_width.append(0.0)

            gp_scaling = 500 / max(group_pop)
            print(gp_scaling, 'gp_scaline')
            group_pop_scale = group_pop * gp_scaling

            ax_i.scatter(node_pos[:, 0], node_pos[:, 1], s=group_pop_scale, c=pt, cmap='viridis_r', edgecolors=c_edge,
                         alpha=1, zorder=3, linewidth=l_width)
            # for ii in range(node_pos.shape[0]):
            # ax_i.text(node_pos[ii, 0] + 0.5, node_pos[ii, 1] + 0.5, 'c' + str(ii), color='black', zorder=4)

            title_pt = title_list[i]
            ax_i.set_title(title_pt)

    def accuracy(self, onevsall=1):

        true_labels = self.true_label
        Index_dict = {}
        PARC_labels = self.labels
        N = len(PARC_labels)
        n_cancer = list(true_labels).count(onevsall)
        n_pbmc = N - n_cancer

        for k in range(N):
            Index_dict.setdefault(PARC_labels[k], []).append(true_labels[k])
        num_groups = len(Index_dict)
        sorted_keys = list(sorted(Index_dict.keys()))
        error_count = []
        pbmc_labels = []
        thp1_labels = []
        fp, fn, tp, tn, precision, recall, f1_score = 0, 0, 0, 0, 0, 0, 0

        for kk in sorted_keys:
            vals = [t for t in Index_dict[kk]]
            majority_val = self.func_mode(vals)
            if majority_val == onevsall: print('cluster', kk, ' has majority', onevsall, 'with population', len(vals))
            if kk == -1:
                len_unknown = len(vals)
                print('len unknown', len_unknown)
            if (majority_val == onevsall) and (kk != -1):
                thp1_labels.append(kk)
                fp = fp + len([e for e in vals if e != onevsall])
                tp = tp + len([e for e in vals if e == onevsall])
                list_error = [e for e in vals if e != majority_val]
                e_count = len(list_error)
                error_count.append(e_count)
            elif (majority_val != onevsall) and (kk != -1):
                pbmc_labels.append(kk)
                tn = tn + len([e for e in vals if e != onevsall])
                fn = fn + len([e for e in vals if e == onevsall])
                error_count.append(len([e for e in vals if e != majority_val]))

        predict_class_array = np.array(PARC_labels)
        PARC_labels_array = np.array(PARC_labels)
        number_clusters_for_target = len(thp1_labels)
        for cancer_class in thp1_labels:
            predict_class_array[PARC_labels_array == cancer_class] = 1
        for benign_class in pbmc_labels:
            predict_class_array[PARC_labels_array == benign_class] = 0
        predict_class_array.reshape((predict_class_array.shape[0], -1))
        error_rate = sum(error_count) / N
        n_target = tp + fn
        tnr = tn / n_pbmc
        fnr = fn / n_cancer
        tpr = tp / n_cancer
        fpr = fp / n_pbmc

        if tp != 0 or fn != 0: recall = tp / (tp + fn)  # ability to find all positives
        if tp != 0 or fp != 0: precision = tp / (tp + fp)  # ability to not misclassify negatives as positives
        if precision != 0 or recall != 0:
            f1_score = precision * recall * 2 / (precision + recall)

        majority_truth_labels = np.empty((len(true_labels), 1), dtype=object)
        for cluster_i in set(PARC_labels):
            cluster_i_loc = np.where(np.asarray(PARC_labels) == cluster_i)[0]
            true_labels = np.asarray(true_labels)
            majority_truth = self.func_mode(list(true_labels[cluster_i_loc]))
            majority_truth_labels[cluster_i_loc] = majority_truth

        majority_truth_labels = list(majority_truth_labels.flatten())
        accuracy_val = [error_rate, f1_score, tnr, fnr, tpr, fpr, precision,
                        recall, num_groups, n_target]

        return accuracy_val, predict_class_array, majority_truth_labels, number_clusters_for_target

    def run_PARC(self):
        print('input data has shape', self.data.shape[0], '(samples) x', self.data.shape[1], '(features)')
        self.ncomp = self.data.shape[1]
        pop_list = []
        for item in set(list(self.true_label)):
            pop_list.append([item, list(self.true_label).count(item)])
        # print("population composition", pop_list)
        if self.true_label is None:
            self.true_label = [1] * self.data.shape[0]
        list_roc = []

        time_start_total = time.time()

        time_start_knn = time.time()
        self.knn_struct = self.make_knn_struct()
        time_end_knn_struct = time.time() - time_start_knn
        # Query dataset, k - number of closest elements (returns 2 numpy arrays)
        self.run_subPARC()
        run_time = time.time() - time_start_total
        print('time elapsed {:.1f} seconds'.format(run_time))

        targets = list(set(self.true_label))
        N = len(list(self.true_label))
        self.f1_accumulated = 0
        self.f1_mean = 0
        self.stats_df = pd.DataFrame({'jac_std_global': [self.jac_std_global], 'dist_std_local': [self.dist_std_local],
                                      'runtime(s)': [run_time]})
        self.majority_truth_labels = []
        if len(targets) > 1:
            f1_accumulated = 0
            f1_acc_noweighting = 0
            for onevsall_val in targets:
                # print('target is', onevsall_val)
                vals_roc, predict_class_array, majority_truth_labels, numclusters_targetval = self.accuracy(
                    onevsall=onevsall_val)
                f1_current = vals_roc[1]
                print('target', onevsall_val, 'has f1-score of %.2f' % (f1_current * 100))
                f1_accumulated = f1_accumulated + f1_current * (list(self.true_label).count(onevsall_val)) / N
                f1_acc_noweighting = f1_acc_noweighting + f1_current

                list_roc.append(
                    [self.jac_std_global, self.dist_std_local, onevsall_val] + vals_roc + [numclusters_targetval] + [
                        run_time])

            f1_mean = f1_acc_noweighting / len(targets)
            print("f1-score (unweighted) mean %.2f" % (f1_mean * 100), '%')
            # print('f1-score weighted (by population) %.2f' % (f1_accumulated * 100), '%')

            df_accuracy = pd.DataFrame(list_roc,
                                       columns=['jac_std_global', 'dist_std_local', 'onevsall-target', 'error rate',
                                                'f1-score', 'tnr', 'fnr',
                                                'tpr', 'fpr', 'precision', 'recall', 'num_groups',
                                                'population of target', 'num clusters', 'clustering runtime'])

            self.f1_accumulated = f1_accumulated
            self.f1_mean = f1_mean
            self.stats_df = df_accuracy
            self.majority_truth_labels = majority_truth_labels
        return


def run_palantir_func_human34(ad, ncomps, knn, tsne, revised_clus, start_cell='c4823'):
    norm_df_pal = pd.DataFrame(ad.X)
    # print('norm df', norm_df_pal)
    new = ['c' + str(i) for i in norm_df_pal.index]
    norm_df_pal.index = new
    norm_df_pal.columns = [i for i in ad.var_names]
    pca_projections, _ = palantir.utils.run_pca(norm_df_pal, n_components=ncomps)

    sc.tl.pca(ad, svd_solver='arpack')
    dm_res = palantir.utils.run_diffusion_maps(pca_projections, n_components=ncomps, knn=knn)

    ms_data = palantir.utils.determine_multiscale_space(dm_res)  # n_eigs is determined using eigengap
    print('ms data', ms_data.shape)
    # tsne =  pd.DataFrame(tsnem)#palantir.utils.run_tsne(ms_data)
    tsne.index = new
    # print(type(tsne))
    str_true_label = pd.Series(revised_clus, index=norm_df_pal.index)

    palantir.plot.plot_cell_clusters(tsne, str_true_label)

    # start_cell = 'c4823'  # '#C108 for M12 connected' #M8n1000d1000 start - c107 #c1001 for bifurc n2000d1000 #disconnected n1000 c108, "C1 for M10 connected" # c10 for bifurcating_m4_n2000d1000

    pr_res = palantir.core.run_palantir(ms_data, early_cell=start_cell, num_waypoints=1200, knn=knn)
    palantir.plot.plot_palantir_results(pr_res, tsne, knn, ncomps)
    # plt.show()
    imp_df = palantir.utils.run_magic_imputation(norm_df_pal, dm_res)
    # imp_df.to_csv('/home/shobi/Trajectory/Datasets/HumanCD34/MAGIC_palantir_knn30ncomp100.csv')

    genes = ['GATA1', 'GATA2', 'ITGA2B']  # , 'SPI1']#['CD34','GATA1', 'IRF8','ITGA2B']
    gene_trends = palantir.presults.compute_gene_trends(pr_res, imp_df.loc[:, genes])
    palantir.plot.plot_gene_trends(gene_trends)
    genes = ['MPO', 'ITGAX', 'IRF8', 'CSF1R', 'IL3RA']  # 'CD34','MPO', 'CD79B'
    gene_trends = palantir.presults.compute_gene_trends(pr_res, imp_df.loc[:, genes])
    palantir.plot.plot_gene_trends(gene_trends)
    plt.show()


def slalom_human():
    import os
    import slalom
    from slalom import plotFactors, plotRelevance, plotLoadings, saveFA, dumpFA
    data_dir = '/home/shobi/Trajectory/Datasets/'

    ad = sc.read(
        '/home/shobi/Trajectory/Datasets/HumanCD34/human_cd34_bm_rep1.h5ad')  # 5780 cells x 14651 genes Human Replicate 1. Male african american, 38 years
    df_ = pd.DataFrame(ad.X)
    df_.columns = [i for i in ad.var_names]

    annoDB = 'custom'  # ''MSigDB'
    annoFile = os.path.join(data_dir, 'geneset.gmt')

    data_slalom = slalom.utils.load_txt(df=df_.T, annoFiles=annoFile, annoDBs=annoDB)

    print("Loaded {:d} cells, {:d} genes".format(data_slalom['Y'].shape[0], data_slalom['Y'].shape[1]))
    print("Annotation: {:d} terms".format(len(data_slalom['terms'])))
    print('data terms', data_slalom['terms'])
    print(data_slalom['genes'])
    print(data_slalom['lab'])
    # I: indicator matrix that assigns genes to pathways
    I = data_slalom['I']  # if loaded from the hdf file change to I = data['IMSigDB']
    # Y: log expresison values
    Y = data_slalom['Y']
    # terms: ther names of the terms
    terms = data_slalom['terms']
    print("terms", terms)
    # gene_ids: the ids of the genes in Y
    gene_ids = data_slalom['genes']
    print('gene_ids', gene_ids)
    print(I.shape, Y.shape, terms.shape)
    # initialize FA instance, here using a Gaussian noise model and fitting 3 dense hidden factors
    FA = slalom.initFA(Y, terms, I, gene_ids=gene_ids, noise='gauss', nHidden=3, minGenes=1)

    FA.train()

    # print diagnostics
    FA.printDiagnostics()
    fig = plotRelevance(FA, madFilter=0)
    # idx=FA.getTermIndex(['G2m checkpoint', 'P53 pathway'])
    # print('idx',idx)
    corrected_data = FA.regressOut(
        terms=['M phase', 'Dna replication', 'Chromosome segregation', 'M phase of mitotic cell cycle',
               'Organelle fission'])
    print('corrected_data.shape', corrected_data.shape)
    full_matrix = df_.copy()
    print(full_matrix.head)
    annotated_genes = np.array(data_slalom['genes'])[np.sum(data_slalom['I'], axis=1) != 0]
    print('annotated genes', len(annotated_genes), annotated_genes)
    full_matrix[annotated_genes] = corrected_data
    print('full shape ', full_matrix)
    return full_matrix


def main_Human(ncomps=100, knn=30, p0_random_seed=4, run_palantir_func=False):
    dict_abb = {'Basophils': 'BASO1', 'CD4+ Effector Memory': 'TCEL7', 'Colony Forming Unit-Granulocytes': 'GRAN1',
                'Colony Forming Unit-Megakaryocytic': 'MEGA1', 'Colony Forming Unit-Monocytes': 'MONO1',
                'Common myeloid progenitors': "CMP", 'Early B cells': "PRE_B2", 'Eosinophils': "EOS2",
                'Erythroid_CD34- CD71+ GlyA-': "ERY2", 'Erythroid_CD34- CD71+ GlyA+': "ERY3",
                'Erythroid_CD34+ CD71+ GlyA-': "ERY1", 'Erythroid_CD34- CD71lo GlyA+': 'ERY4',
                'Granulocyte/monocyte progenitors': "GMP", 'Hematopoietic stem cells_CD133+ CD34dim': "HSC1",
                'Hematopoietic stem cells_CD38- CD34+': "HSC2",
                'Mature B cells class able to switch': "B_a2", 'Mature B cells class switched': "B_a4",
                'Mature NK cells_CD56- CD16- CD3-': "Nka3", 'Monocytes': "MONO2",
                'Megakaryocyte/erythroid progenitors': "MEP", 'Myeloid Dendritic Cells': 'mDC', 'Naïve B cells': "B_a1",
                'Plasmacytoid Dendritic Cells': "pDC", 'Pro B cells': 'PRE_B3'}

    ncomps = ncomps  # 40 ncomps and 20KNN works well
    knn = knn  # 30
    p0_random_seed = p0_random_seed
    string_ = 'ncomp =' + str(ncomps) + ' knn=' + str(knn) + ' randseed=' + str(p0_random_seed)
    # print('ncomp =', ncomps, ' knn=', knn, ' randseed=', p0_random_seed)
    print(colored(string_, 'blue'))
    nover_labels = pd.read_csv('/home/shobi/Trajectory/Datasets/HumanCD34/Nover_Cor_PredFine_notLogNorm.csv')[
        'x'].values.tolist()
    nover_labels = [dict_abb[i] for i in nover_labels]
    for i in list(set(nover_labels)):
        print('the population of ', i, 'is ', nover_labels.count(i))
    parc53_labels = pd.read_csv('/home/shobi/Trajectory/Datasets/HumanCD34/Nover_Cor_Parc53_set1.csv')[
        'x'].values.tolist()

    parclabels_all = pd.read_csv('/home/shobi/Trajectory/Datasets/HumanCD34/parclabels_all_set1.csv')[
        'parc'].values.tolist()
    parc_dict_nover = {}
    for i, c in enumerate(parc53_labels):
        parc_dict_nover[i] = dict_abb[c]
    parclabels_all = [parc_dict_nover[ll] for ll in parclabels_all]
    # print('all', len(parclabels_all))

    ad = sc.read(
        '/home/shobi/Trajectory/Datasets/HumanCD34/human_cd34_bm_rep1.h5ad')
    # 5780 cells x 14651 genes Human Replicate 1. Male african american, 38 years
    print('h5ad  ad size', ad)
    colors = pd.Series(ad.uns['cluster_colors'])
    colors['10'] = '#0b128f'
    ct_colors = pd.Series(ad.uns['ct_colors'])
    list_var_names = ad.var_names
    # print(list_var_names)
    ad.uns['iroot'] = np.flatnonzero(ad.obs_names == ad.obs['palantir_pseudotime'].idxmin())[0]
    print('iroot', np.flatnonzero(ad.obs_names == ad.obs['palantir_pseudotime'].idxmin())[0])

    tsne = pd.DataFrame(ad.obsm['tsne'], index=ad.obs_names, columns=['x', 'y'])
    tsnem = ad.obsm['tsne']
    palantir_tsne_df = pd.DataFrame(tsnem)
    palantir_tsne_df.to_csv('/home/shobi/Trajectory/Datasets/HumanCD34/palantir_tsne.csv')
    revised_clus = ad.obs['clusters'].values.tolist().copy()
    loc_DCs = [i for i in range(5780) if ad.obs['clusters'].values.tolist()[i] == '7']
    for loc_i in loc_DCs:
        if ad.obsm['palantir_branch_probs'][loc_i, 5] > ad.obsm['palantir_branch_probs'][
            loc_i, 2]:  # if prob that cDC > pDC, then relabel as cDC
            revised_clus[loc_i] = '10'
    revised_clus = [int(i) for i in revised_clus]
    # magic_df = ad.obsm['MAGIC_imputed_data']

    # ad.X: Filtered, normalized and log transformed count matrix
    # ad.raw: Filtered raw count matrix
    # print('before extra filtering' ,ad.shape)
    # sc.pp.filter_genes(ad, min_cells=10)
    # print('after extra filtering', ad.shape)
    adata_counts = sc.AnnData(
        ad.X)  # slalom_human())#(ad.X)  # ad.X is filtered, lognormalized,scaled// ad.raw.X is the filtered but not pre-processed
    adata_counts.obs_names = ad.obs_names
    adata_counts.var_names = ad.var_names
    # sc.pp.recipe_zheng17(adata_counts, n_top_genes=1000, log=True) #using this or the .X scaled version is pretty much the same.
    sc.tl.pca(adata_counts, svd_solver='arpack', n_comps=ncomps)
    marker = ['x', '+', (5, 0), '>', 'o', (5, 2)]
    import colorcet as cc
    if run_palantir_func == True:
        run_palantir_func_human34(ad, ncomps, knn, tsne, revised_clus, start_cell='c4823')

    # tsnem = TSNE().fit_transform(adata_counts.obsm['X_pca'])
    '''
    f, (ax1, ax2, ax3) = plt.subplots(1, 3, sharey=True)

    line = np.linspace(0, 1, len(set(revised_clus)))

    for color, group in zip(line, set(revised_clus)):
        where = np.where(np.array(revised_clus) == group)[0]
        ax1.scatter(tsnem[where, 0], tsnem[where, 1], label=group, c=np.asarray(plt.cm.jet(color)).reshape(-1, 4))
    ax1.legend()
    ax1.set_title('Palantir Phenograph Labels')


    import colorcet as cc
    marker = ['x', '+', (5, 0), '>', 'o', (5, 2)]
    line_nover = np.linspace(0, 1, len(set(nover_labels)))
    col_i = 0
    for color, group in zip(line_nover, set(nover_labels)):
        where = np.where(np.array(nover_labels) == group)[0]
        marker_x = marker[random.randint(0, 5)]
        # ax2.scatter(tsnem[where, 0],tsnem[where, 1], label=group, c=plt.cm.nipy_spectral(color), marker = marker_x, alpha=0.5)

        ax2.scatter(tsnem[where, 0], tsnem[where, 1], label=group, c=cc.glasbey_dark[col_i], marker=marker_x,
                    alpha=0.5)
        col_i = col_i + 1
    ax2.legend(fontsize=6)
    ax2.set_title('Novershtern Corr. Labels')

    line = np.linspace(0, 1, len(set(parclabels_all)))
    col_i = 0
    for color, group in zip(line, set(parclabels_all)):
        where = np.where(np.array(parclabels_all) == group)[0]
        ax3.scatter(tsnem[where, 0], tsnem[where, 1], label=group, c=cc.glasbey_dark[col_i], alpha=0.5)
        col_i = col_i + 1
    ax3.legend()
    ax3.set_title('Parc53 Nover Labels')
    # plt.show()
    '''
    '''
    plt.figure(figsize=[5, 5])
    plt.title('palantir, ncomps = ' + str(ncomps) + ' knn' + str(knn))

    for group in set(revised_clus):
        loc_group = np.where(np.asarray(revised_clus) == group)[0]
        plt.scatter(tsnem[loc_group, 0], tsnem[loc_group, 1], s=5, color=colors[group], label=group)
    ax = plt.gca()
    ax.set_axis_off()
    ax.legend(fontsize=6)

    '''

    gene_list = [
        'ITGAX']  # ['GATA1', 'GATA2', 'ITGA2B', 'CSF1R', 'MPO', 'CD79B', 'SPI1', 'IRF8', 'CD34', 'IL3RA', 'ITGAX', 'IGHD',
    # 'CD27', 'CD14', 'CD22', 'ITGAM', 'CLC', 'MS4A3', 'FCGR3A', 'CSF1R']
    for gene_name in gene_list:  # 'GATA2',
        loc_gata = np.where(np.asarray(ad.var_names) == gene_name)[0][0]
        print('gene name', gene_name, loc_gata)
    # print('xpca',norm_df['X_pca'])
    true_label = nover_labels  # revised_clus

    print('p0 random seed', p0_random_seed)
    # df_temp_write  = pd.DataFrame(adata_counts.obsm['X_pca'][:, 0:200])
    # df_temp_write.to_csv("/home/shobi/Trajectory/Datasets/HumanCD34/Human_CD34_200PCA.csv")
    p0 = PARC(adata_counts.obsm['X_pca'][:, 0:ncomps], true_label, jac_std_global=0.15, dist_std_local=1, knn=knn,
              too_big_factor=0.4,
              pseudotime=True, path="/home/shobi/Trajectory/Datasets/HumanCD34/",
              root_user=4823, dataset='humanCD34', preserve_disconnected=True, random_seed=p0_random_seed,
              do_magic_bool=True, is_coarse=True)  # *.4 root=1,
    p0.run_PARC()
    super_labels = p0.labels
    df_ = pd.DataFrame(ad.X)
    df_.columns = [i for i in ad.var_names]
    print('start magic')
    gene_list_magic = ['IL3RA', 'IRF8', 'GATA1', 'GATA2', 'ITGA2B', 'MPO', 'CD79B', 'SPI1', 'CD34', 'CSF1R', 'ITGAX']
    df_magic = p0.do_magic(df_, magic_steps=3, gene_list=gene_list_magic)
    print('end magic', df_magic.shape)

    print('super labels', set(super_labels))
    ad.obs['parc0_label'] = [str(i) for i in super_labels]
    magic_ad = ad.obsm['MAGIC_imputed_data']
    magic_ad = sc.AnnData(magic_ad)
    magic_ad.obs_names = ad.obs_names
    magic_ad.var_names = ad.var_names
    magic_ad.obs['parc0_label'] = [str(i) for i in super_labels]
    marker_genes = {"ERY": ['GATA1', 'GATA2', 'ITGA2B'], "BCell": ['IGHD', 'CD22'],
                    "DC": ['IRF8', 'IL3RA', 'IRF4', 'CSF2RA', 'ITGAX'],
                    "MONO": ['CD14', 'SPI1', 'MPO', 'IL12RB1', 'IL13RA1', 'C3AR1', 'FCGR3A'], 'HSC': ['CD34']}

    print('make the p0 matrix plot')
    sc.pl.matrixplot(magic_ad, marker_genes, groupby='parc0_label', dendrogram=True)
    '''

    sc.tl.rank_genes_groups(ad, groupby='parc0_label', use_raw=True,
                            method='wilcoxon', n_genes=10)  # compute differential expression
    sc.pl.rank_genes_groups_heatmap(ad, n_genes=10, groupby="parc0_label", show_gene_labels=True, use_raw=False)
    sc.pl.rank_genes_groups_tracksplot(ad, groupby='parc0_label', n_genes = 3)  # plot the result

    print('show the matrix plot')
    '''
    super_edges = p0.edgelist_maxout  # p0.edgelist
    super_pt = p0.scaled_hitting_times  # pseudotime pt

    p = hnswlib.Index(space='l2', dim=adata_counts.obsm['X_pca'][:, 0:ncomps].shape[1])
    p.init_index(max_elements=adata_counts.obsm['X_pca'][:, 0:ncomps].shape[0], ef_construction=200, M=16)
    p.add_items(adata_counts.obsm['X_pca'][:, 0:ncomps])
    p.set_ef(50)

    tsi_list = []  # find the single-cell which is nearest to the average-location of a terminal cluster
    for tsi in p0.terminal_clusters:
        loc_i = np.where(super_labels == tsi)[0]
        temp = np.mean(adata_counts.obsm['X_pca'][:, 0:ncomps][loc_i], axis=0)
        labelsq, distances = p.knn_query(temp, k=1)
        # print(labelsq[0])
        tsi_list.append(labelsq[0][0])

    p1 = PARC(adata_counts.obsm['X_pca'][:, 0:ncomps], true_label, jac_std_global=0.15, dist_std_local=1, knn=knn,
              too_big_factor=0.05,
              path="/home/shobi/Trajectory/Datasets/HumanCD34/", pseudotime=True,
              super_cluster_labels=super_labels, super_node_degree_list=p0.node_degree_list,
              super_terminal_cells=tsi_list, root_user=4823,
              x_lazy=0.99, alpha_teleport=0.99, dataset='humanCD34', preserve_disconnected=True,
              super_terminal_clusters=p0.terminal_clusters, is_coarse=False, full_neighbor_array=p0.full_neighbor_array,
              ig_full_graph=p0.ig_full_graph,
              csr_array_pruned=p0.csr_array_pruned)  # *.4super_terminal_cells = tsi_list #3root=1,
    p1.run_PARC()
    labels = p1.labels

    ad.obs['parc1_label'] = [str(i) for i in labels]

    tsi_list = []  # find the single-cell which is nearest to the average-location of a terminal cluster
    for tsi in p1.revised_super_terminal_clusters:
        loc_i = np.where(super_labels == tsi)[0]
        temp = np.mean(adata_counts.obsm['X_pca'][:, 0:ncomps][loc_i], axis=0)
        labelsq, distances = p.knn_query(temp, k=1)
        print(labelsq[0])
        tsi_list.append(labelsq[0][0])

    '''
    sc.tl.rank_genes_groups(ad, groupby='parc1_label', use_raw=True,
                            method='wilcoxon', n_genes=10)  # compute differential expression

    sc.pl.matrixplot(ad, marker_genes, groupby='parc1_label', use_raw=False)
    sc.pl.rank_genes_groups_heatmap(ad, n_genes=3, groupby="parc1_label", show_gene_labels=True, use_raw=False)
    '''
    label_df = pd.DataFrame(labels, columns=['parc'])
    # label_df.to_csv('/home/shobi/Trajectory/Datasets/HumanCD34/parclabels.csv', index=False)
    gene_ids = adata_counts.var_names

    obs = ad.raw.X.toarray()
    print('shape obs', obs.shape)
    obs = pd.DataFrame(obs, columns=gene_ids)
    #    obs['parc']=p1.labels
    obs['louvain'] = revised_clus

    # obs_average = obs.groupby('parc', as_index=True).mean()
    obs_average = obs.groupby('louvain', as_index=True).mean()
    # print(obs_average.head())
    # obs_average.to_csv('/home/shobi/Trajectory/Datasets/HumanCD34/louvain_palantir_average.csv', index=False)
    ad_obs = sc.AnnData(obs_average)
    ad_obs.var_names = gene_ids
    ad_obs.obs['parc'] = [i for i in range(len(set(revised_clus)))]  # p1.labels instaed of revised_clus

    # sc.write('/home/shobi/Trajectory/Datasets/HumanCD34/louvain_palantir_average.h5ad',ad_obs)
    # fig_0, ax_0 = plt.subplots()
    loaded_magic_df = pd.read_csv('/home/shobi/Trajectory/Datasets/HumanCD34/MAGIC_palantir_knn30ncomp100_subset.csv')
    # loaded_magic_df.head()
    for gene_name in ['ITGA2B', 'IL3RA', 'ITGAX',
                      'IRF8']:  # ['GATA1', 'GATA2', 'ITGA2B', 'MPO', 'CD79B','IRF8','SPI1', 'CD34','CSF1R','IL3RA','IRF4', 'CSF2RA','ITGAX']:
        print('gene name', gene_name)
        # DC markers https://www.cell.com/pb-assets/products/nucleus/nucleus-phagocytes/rnd-systems-dendritic-cells-br.pdf
        gene_name_dict = {'GATA1': 'GATA1', 'GATA2': 'GATA2', 'ITGA2B': 'CD41 (Mega)', 'MPO': 'MPO (Mono)',
                          'CD79B': 'CD79B (B)', 'IRF8': 'IRF8 (DC)', 'SPI1': 'PU.1', 'CD34': 'CD34',
                          'CSF1R': 'CSF1R (pDC. Up then Down in cDC)', 'IL3RA': 'CD123 (pDC)', 'IRF4': 'IRF4 (pDC)',
                          'ITGAX': 'ITGAX (cDCs)', 'CSF2RA': 'CSF2RA (cDC)'}

        # loc_gata = np.where(np.asarray(ad.var_names) == gene_name)[0][0]
        # magic_ad = ad.obsm['MAGIC_imputed_data'][:, loc_gata]
        # magic_ad=loaded_magic_df[gene_name]
        subset_ = df_magic[gene_name].values
        print(subset_.shape)
        # print('shapes of magic_ad 1 and 2', magic_ad.shape,subset_.shape)
        # p1.get_gene_expression(magic_ad,title_gene = gene_name_dict[gene_name])
        p1.get_gene_expression(subset_, title_gene=gene_name_dict[gene_name] + 'VIA MAGIC')

    print('start tsne')
    n_downsample = 4000
    if len(labels) > n_downsample:
        # idx = np.random.randint(len(labels), size=4000)
        np.random.seed(2357)
        idx = np.random.choice(a=np.arange(0, len(labels)), size=5780, replace=False, p=None)
        super_labels = np.asarray(super_labels)[idx]
        labels = list(np.asarray(labels)[idx])
        print('labels p1', len(labels), set(labels))
        true_label = list(np.asarray(true_label)[idx])
        sc_pt_markov = list(np.asarray(p1.single_cell_pt_markov)[idx])
        # graph_hnsw = p0.knngraph_visual()
        embedding = tsnem[idx, :]  # TSNE().fit_transform(adata_counts.obsm['X_pca'][idx, :])
        # embedding = umap.UMAP().fit_transform(adata_counts.obsm['X_pca'][idx, 0:20])
        print('size of downsampled embedding', embedding.shape)

    else:
        # embedding = TSNE().fit_transform(adata_counts.obsm['X_pca'][:,0:15])
        # print('tsne input size', adata_counts.obsm['X_pca'].shape)
        embedding = tsnem  # umap.UMAP().fit_transform(adata_counts.obsm['X_pca'][:,0:20])
        idx = np.random.randint(len(labels), size=len(labels))
    print('end tsne')

    knn_hnsw, ci_list = sc_loc_ofsuperCluster_embeddedspace(embedding, p0, p1, idx)
    super_clus_ds_PCA_loc = sc_loc_ofsuperCluster_PCAspace(p0, p1, idx)
    draw_trajectory_gams(embedding, super_clus_ds_PCA_loc, labels, super_labels, super_edges,
                         p1.x_lazy, p1.alpha_teleport, sc_pt_markov, true_label, knn=p0.knn,
                         final_super_terminal=p1.revised_super_terminal_clusters,
                         sub_terminal_clusters=p1.terminal_clusters,
                         title_str='Hitting times: Markov Simulation on biased edges', ncomp=ncomps)

    # final_super_terminal=p0.terminal clusters
    '''
    draw_trajectory_dimred(embedding, ci_list, labels, super_labels, super_edges,
                         p1.x_lazy, p1.alpha_teleport, sc_pt_markov, true_label, knn=p0.knn,
                         final_super_terminal=p0.terminal_clusters,
                         title_str='Hitting times: Markov Simulation on biased edges', ncomp=ncomps)
    plt.show()
    '''

    num_group = len(set(true_label))

    line = np.linspace(0, 1, num_group)
    lineP0 = np.linspace(0, 1, len(set(p0.labels)))
    lineP1 = np.linspace(0, 1, len(set(p1.labels)))

    # find the single-cell which is nearest to the average-location of a terminal cluster - for just the sub-set of downsampled points in the corresponding PCA-space
    new_tsi_list = []
    # find the single-cell which is nearest to the average-location of a terminal cluster
    # TODO make a knn in the downsampled PCA-space
    X_ds = adata_counts.obsm['X_pca'][:, 0:ncomps][idx]
    p_ds = hnswlib.Index(space='l2', dim=ncomps)
    p_ds.init_index(max_elements=X_ds.shape[0], ef_construction=200, M=16)
    p_ds.add_items(X_ds)
    p_ds.set_ef(50)

    for tsi_item in tsi_list:
        labelsq, distances = p_ds.knn_query(adata_counts.obsm['X_pca'][:, 0:ncomps][tsi_item, :], k=1)
        new_tsi_list.append(labelsq[0][0])
    new_tsi_list = super_clus_ds_PCA_loc
    # for old_tsi_i in tsi_list:
    # temp = np.mean(adata_counts.obsm['X_pca'][:, 0:ncomps][loc_i], axis=0)
    # labelsq, distances = p1.knn_struct.query(.knn_query(temp, k=1)
    # print(labelsq[0])
    # tsi_list.append(labelsq[0][0])
    f, (ax1, ax2, ax3) = plt.subplots(1, 3, sharey=True)
    ff, (ax11, ax22) = plt.subplots(1, 2, sharey=True)
    col_i = 0
    for color, group in zip(line, set(true_label)):
        marker_x = marker[random.randint(0, 5)]
        where = np.where(np.asarray(true_label) == group)[0]
        # ax1.scatter(embedding[where, 0], embedding[where, 1], label=group, c=plt.cm.jet(color))
        ax1.scatter(embedding[where, 0], embedding[where, 1], label=group, c=cc.glasbey_dark[col_i], marker=marker_x,
                    alpha=0.5)
        col_i = col_i + 1

    ax1.legend(fontsize=6)
    ax1.set_title('true labels')

    for color, group in zip(lineP0, set(p0.labels)):
        where = np.where(super_labels == group)[0]
        ax11.scatter(embedding[where, 0], embedding[where, 1], label=group,
                     c=np.asarray(plt.cm.jet(color)).reshape(-1, 4))
    ax11.legend(fontsize=6)
    ax11.set_title('p0 labels')

    for color, group in zip(lineP1, set(p1.labels)):
        where = np.where(labels == group)[0]
        ax22.scatter(embedding[where, 0], embedding[where, 1], label=group,
                     c=np.asarray(plt.cm.jet(color)).reshape(-1, 4))
    ax22.legend(fontsize=6)
    ax22.set_title('p1 labels')

    ax3.set_title("Markov Sim PT ncomps:" + str(ncomps) + '. knn:' + str(knn))
    ax3.scatter(embedding[:, 0], embedding[:, 1], c=sc_pt_markov, cmap='viridis_r')

    ax2.set_title(
        "terminal clus from P0 super clus:" + str(ncomps) + '. knn:' + str(knn) + 'randseed' + str(p0_random_seed))
    ax2.scatter(embedding[:, 0], embedding[:, 1], c=sc_pt_markov, cmap='viridis_r')

    jj = 0
    for ti, ti_sub in zip(p1.revised_super_terminal_clusters, p1.terminal_clusters):  # p0.terminal_clusters:
        loc_i = np.where(super_labels == ti)[0]
        val_pt = [sc_pt_markov[i] for i in loc_i]
        th_pt = np.percentile(val_pt, 0)  # 50
        loc_i = [loc_i[i] for i in range(len(val_pt)) if val_pt[i] >= th_pt]
        x = [embedding[xi, 0] for xi in loc_i]
        y = [embedding[yi, 1] for yi in loc_i]
        labelsq, distances = knn_hnsw.knn_query(np.array([np.mean(x), np.mean(y)]), k=1)
        x = embedding[labelsq[0], 0]
        y = embedding[labelsq[0], 1]
        # ax2.scatter(np.mean(x), np.mean(y), label='ts' + str(ti)+'M'+str(maj), c='red', s=15)
        # ax2.scatter(x, y, label='TS' + str(ti), c='red', s=10)
        # ax3.scatter(x, y, label='TS' + str(ti), c='red', s=10)
        print(super_clus_ds_PCA_loc[jj], 'super_clus_ds_PCA_loc[jj]', embedding[super_clus_ds_PCA_loc[jj], :])
        ax2.scatter(embedding[super_clus_ds_PCA_loc[ti], 0], embedding[super_clus_ds_PCA_loc[ti], 1],
                    label='TS' + str(ti), c='pink', s=18)  # PCs HNSW
        # ax3.scatter(embedding[new_tsi_list[jj], 0], embedding[new_tsi_list[jj], 1], label='TS' + str(p1.labels[tsi_list[jj]]), c='pink',s=18)

        ax2.text(embedding[super_clus_ds_PCA_loc[ti], 0] + 0.05, embedding[super_clus_ds_PCA_loc[ti], 1] + 0.05,
                 'TS' + str(ti), color='black', zorder=3)
        # ax3.text(np.mean(x) + 0.05, np.mean(y) + 0.05, 'TS' + str(ti), color='black', zorder=3)
        ax2.legend(fontsize=6)

        ax3.scatter(embedding[super_clus_ds_PCA_loc[ti], 0], embedding[super_clus_ds_PCA_loc[ti], 1],
                    label='TS' + str(ti), c='pink', s=18)

        ax3.text(embedding[super_clus_ds_PCA_loc[ti], 0] + 0.05, embedding[super_clus_ds_PCA_loc[ti], 1] + 0.05,
                 'TS' + str(ti_sub), color='black', zorder=3)

        jj = jj + 1
    jj = 0

    for ti in p1.terminal_clusters:
        print('terminal ti', ti)

        jj = jj + 1

    draw_sc_evolution_trajectory_dijkstra(p1, embedding, knn_hnsw, p0.full_graph_shortpath, idx,
                                          adata_counts.obsm['X_pca'][:, 0:ncomps])

    plt.show()


def main_Toy(ncomps=100, knn=30, random_seed=41):
    dataset = "Toy3"  # "ToyCyclic"#"Toy4"#"Toy3"  # ""Toy1" # GermlineLi #Toy1
    print('dataset, ncomps, knn, seed', dataset, ncomps, knn, random_seed)
    ## Dataset Germline Li https://zenodo.org/record/1443566#.XZlhEkEzZ5y
    if dataset == "GermlineLine":
        df_expression_ids = pd.read_csv("/home/shobi/Trajectory/Code/Rcode/germline_human_female_weeks_li.csv", 'rt',
                                        delimiter=",")
        print(df_expression_ids.shape)
        # print(df_expression_ids[['cell_id',"week","ACTG2","STK31"]])[10:12]
        df_counts = pd.read_csv("/home/shobi/Trajectory/Code/Rcode/germline_human_female_weeks_li_filteredcounts.csv",
                                'rt', delimiter=",")
        df_ids = pd.read_csv("/home/shobi/Trajectory/Code/Rcode/germline_human_female_weeks_li_labels.csv", 'rt',
                             delimiter=",")
        # print(df_counts.shape, df_counts.head() ,df_ids.shape)
        # X_counts = df_counts.values
        # print(X_counts.shape)
        # varnames = pd.Categorical(list(df_counts.columns))

        adata_counts = sc.AnnData(df_counts, obs=df_ids)
        print(adata_counts.obs)
        sc.pp.filter_cells(adata_counts, min_counts=1)
        print(adata_counts.n_obs)
        sc.pp.filter_genes(adata_counts, min_counts=1)  # only consider genes with more than 1 count
        print(adata_counts.X.shape)
        sc.pp.normalize_per_cell(  # normalize with total UMI count per cell
            adata_counts, key_n_counts='n_counts_all')
        print(adata_counts.X.shape, len(list(adata_counts.var_names)))

        filter_result = sc.pp.filter_genes_dispersion(  # select highly-variable genes
            adata_counts.X, flavor='cell_ranger', n_top_genes=1000, log=False)
        print(adata_counts.X.shape, len(list(adata_counts.var_names)))  # , list(adata_counts.var_names))

        adata_counts = adata_counts[:, filter_result.gene_subset]
        print(adata_counts.X.shape, len(list(adata_counts.var_names)))  # ,list(adata_counts.var_names))
        # subset the genes
        sc.pp.normalize_per_cell(adata_counts)  # renormalize after filtering
        sc.pp.log1p(adata_counts)  # log transform: adata_counts.X = log(adata_counts.X + 1)
        sc.pp.scale(adata_counts)  # scale to unit variance and shift to zero mean
        sc.tl.pca(adata_counts, svd_solver='arpack', n_comps=20)

        true_label = list(adata_counts.obs['week'])
        sc.pp.neighbors(adata_counts, n_neighbors=10, n_pcs=20)
        sc.tl.draw_graph(adata_counts)
        sc.pl.draw_graph(adata_counts, color='gender_week', legend_loc='right margin', palette='jet')

    ## Dataset Paul15 https://scanpy-tutorials.readthedocs.io/en/latest/paga-paul15.html
    if dataset == 'Paul15':
        root_user = "8Mk"
        adata_counts = sc.datasets.paul15()
        sc.pp.recipe_zheng17(adata_counts)
        sc.tl.pca(adata_counts, svd_solver='arpack')
        true_label = list(adata_counts.obs['paul15_clusters'])  # PAUL
        adata_counts.obs['group_id'] = true_label
        # sc.pp.neighbors(adata_counts, n_neighbors=10)
        # sc.tl.draw_graph(adata_counts)
        # sc.pl.draw_graph(adata_counts, color=['paul15_clusters', 'Cma1'], legend_loc='on data')

    if dataset.startswith('Toy'):
        root_user = "M1"  # ["T1_M1", "T2_M1"]#'M1'  # "T1_M1", "T2_M1"] #"T1_M1"
        if dataset == "Toy1":
            df_counts = pd.read_csv("/home/shobi/Trajectory/Datasets/Toy1/toy_bifurcating_M4_n2000d1000.csv",
                                    'rt', delimiter=",")
            df_ids = pd.read_csv("/home/shobi/Trajectory/Datasets/Toy1/toy_bifurcating_M4_n2000d1000_ids.csv",
                                 'rt', delimiter=",")
        if dataset == "Toy2":
            df_counts = pd.read_csv("/home/shobi/Trajectory/Datasets/Toy2/toy_multifurcating_n1000.csv", 'rt',
                                    delimiter=",")
            df_ids = pd.read_csv("/home/shobi/Trajectory/Datasets/Toy2/toy_multifurcating_n1000_ids.csv", 'rt',
                                 delimiter=",")
        if dataset == "Toy3":
            df_counts = pd.read_csv("/home/shobi/Trajectory/Datasets/Toy3/toy_multifurcating_M8_n1000d1000.csv", 'rt',
                                    delimiter=",")
            df_ids = pd.read_csv("/home/shobi/Trajectory/Datasets/Toy3/toy_multifurcating_M8_n1000d1000_ids.csv", 'rt',
                                 delimiter=",")
            start_cell = 'C107'
        if dataset == "ToyCyclic":
            df_counts = pd.read_csv("/home/shobi/Trajectory/Datasets/ToyCyclic/ToyCyclic_M4_n1000d1000.csv", 'rt',
                                    delimiter=",")
            df_ids = pd.read_csv("/home/shobi/Trajectory/Datasets/ToyCyclic/ToyCyclic_M4_n1000d1000_ids.csv", 'rt',
                                 delimiter=",")
            start_cell = 'C1'  # 'C1004'
        if dataset == "Toy4":
            df_counts = pd.read_csv("/home/shobi/Trajectory/Datasets/Toy4/toy_disconnected_M9_n1000d1000.csv", 'rt',
                                    delimiter=",")
            df_ids = pd.read_csv("/home/shobi/Trajectory/Datasets/Toy4/toy_disconnected_M9_n1000d1000_ids.csv", 'rt',
                                 delimiter=",")

        df_ids['cell_id_num'] = [int(s[1::]) for s in df_ids['cell_id']]
        print("shape", df_counts.shape, df_ids.shape)
        df_counts = df_counts.drop('Unnamed: 0', 1)
        df_ids = df_ids.sort_values(by=['cell_id_num'])
        df_ids = df_ids.reset_index(drop=True)
        # df_ids.to_csv("/home/shobi/Trajectory/Datasets/ToyCyclic/ToyCyclic_M4_n3000d1000_sorted.csv")
        # df_ids.to_csv("/home/shobi/Trajectory/Datasets/Toy4/toy_disconnected_M9_n1000d1000_ids_sorted.csv")

        true_label = df_ids['group_id']
        adata_counts = sc.AnnData(df_counts, obs=df_ids)
        # sc.pp.recipe_zheng17(adata_counts, n_top_genes=20) not helpful for toy data

    sc.tl.pca(adata_counts, svd_solver='arpack', n_comps=ncomps)
    '''
    print(np.flatnonzero(adata_counts.obs['group_id'] == 'M1')[0]) #'T1_M1'
    adata_counts.uns['iroot'] = np.flatnonzero(adata_counts.obs['group_id'] == 'M1')[0]

    sc.pp.neighbors(adata_counts, n_neighbors=knn, n_pcs=ncomps)#4
    sc.tl.draw_graph(adata_counts)
    sc.pl.draw_graph(adata_counts, color='group_id', legend_loc='on data') #force-directed layout
    start_dfmap = time.time()
    sc.tl.diffmap(adata_counts, n_comps=ncomps)
    print('time taken to get diffmap given knn', time.time() - start_dfmap)
    sc.pp.neighbors(adata_counts, n_neighbors=knn, use_rep='X_diffmap')#4
    sc.tl.draw_graph(adata_counts)
    sc.pl.draw_graph(adata_counts, color='group_id', legend_loc='on data')
    sc.tl.leiden(adata_counts, resolution=1.0, random_state=10)
    sc.tl.paga(adata_counts, groups='leiden')
    #sc.pl.paga(adata_counts, color=['louvain','group_id'])

    sc.tl.dpt(adata_counts, n_dcs=ncomps)
    sc.pl.paga(adata_counts, color=['leiden', 'group_id', 'dpt_pseudotime'], title=['leiden (knn:'+str(knn)+' ncomps:'+str(ncomps)+')', 'group_id (ncomps:'+str(ncomps)+')','pseudotime (ncomps:'+str(ncomps)+')'])
    #X = df_counts.values


    print(palantir.__file__) #location of palantir source code
    #counts = palantir.io.from_csv("/home/shobi/Trajectory/Datasets/Toy4/toy_disconnected_M9_n1000d1000.csv")
    #counts = palantir.io.from_csv("/home/shobi/Trajectory/Datasets/Toy3/toy_multifurcating_M8_n1000d1000.csv")
    counts = palantir.io.from_csv("/home/shobi/Trajectory/Datasets/ToyCyclic/ToyCyclic_M4_n1000d1000.csv")
    print('counts',counts)
    str_true_label = true_label.tolist()
    str_true_label = [(i[1:]) for i in str_true_label]

    str_true_label = pd.Series(str_true_label, index=counts.index)
    norm_df = counts#palantir.preprocess.normalize_counts(counts)
    pca_projections, _ = palantir.utils.run_pca(norm_df, n_components=ncomps)
    dm_res = palantir.utils.run_diffusion_maps(pca_projections, n_components=ncomps, knn=knn)

    ms_data = palantir.utils.determine_multiscale_space(dm_res) #n_eigs is determined using eigengap

    tsne = palantir.utils.run_tsne(ms_data)

    palantir.plot.plot_cell_clusters(tsne, str_true_label)
    #C108 for M12 connected' #M8n1000d1000 start - c107 #c1001 for bifurc n2000d1000 #disconnected n1000 c108, "C1 for M10 connected" # c10 for bifurcating_m4_n2000d1000
    print('ms data', ms_data)
    pr_res = palantir.core.run_palantir(ms_data, start_cell, num_waypoints=500,knn=knn)
    palantir.plot.plot_palantir_results(pr_res, tsne, n_knn = knn, n_comps=ncomps)
    plt.show()

    # clusters = palantir.utils.determine_cell_clusters(pca_projections)

    '''
    from sklearn.decomposition import PCA
    pca = PCA(n_components=ncomps)
    pc = pca.fit_transform(df_counts)

    p0 = PARC(adata_counts.obsm['X_pca'][:, 0:ncomps], true_label, jac_std_global=0.15, dist_std_local=1, knn=knn,
              too_big_factor=0.3,
              pseudotime=True, path="/home/shobi/Trajectory/Datasets/" + dataset + "/",
              root_user=root_user, preserve_disconnected=True, dataset='toy', random_seed=random_seed)  # *.4 root=2,
    p0.run_PARC()
    super_labels = p0.labels

    super_edges = p0.edgelist
    super_pt = p0.scaled_hitting_times  # pseudotime pt
    # 0.05 for p1 toobig

    p = hnswlib.Index(space='l2', dim=adata_counts.obsm['X_pca'][:, 0:ncomps].shape[1])
    p.init_index(max_elements=adata_counts.obsm['X_pca'][:, 0:ncomps].shape[0], ef_construction=200, M=16)
    p.add_items(adata_counts.obsm['X_pca'][:, 0:ncomps])
    p.set_ef(50)
    tsi_list = []  # find the single-cell which is nearest to the average-location of a terminal cluster in PCA space (
    for tsi in p0.terminal_clusters:
        loc_i = np.where(np.asarray(p0.labels) == tsi)[0]
        val_pt = [p0.single_cell_pt_markov[i] for i in loc_i]
        th_pt = np.percentile(val_pt, 50)  # 50
        loc_i = [loc_i[i] for i in range(len(val_pt)) if val_pt[i] >= th_pt]
        temp = np.mean(adata_counts.obsm['X_pca'][:, 0:ncomps][loc_i], axis=0)
        labelsq, distances = p.knn_query(temp, k=1)
        print(labelsq[0])
        tsi_list.append(labelsq[0][0])

    p1 = PARC(adata_counts.obsm['X_pca'][:, 0:ncomps], true_label, jac_std_global=.15, dist_std_local=1, knn=knn,
              too_big_factor=0.1,
              path="/home/shobi/Trajectory/Datasets/" + dataset + "/", pseudotime=True,
              super_cluster_labels=super_labels, super_node_degree_list=p0.node_degree_list,
              super_terminal_cells=tsi_list, root_user=root_user,
              x_lazy=0.99, alpha_teleport=0.99, preserve_disconnected=True, dataset='toy',
              super_terminal_clusters=p0.terminal_clusters, random_seed=random_seed)  # root=1,
    # in the case of TOY DATA: P1 WORKS MUCH BETTER WHEN ONLY USING SUPER_TERMINAL_CLUS... O/W need to omit pruning

    p1.run_PARC()
    labels = p1.labels

    # p1 = PARC(adata_counts.obsm['X_pca'], true_label, jac_std_global=1, knn=5, too_big_factor=0.05, anndata= adata_counts, small_pop=2)
    # p1.run_PARC()
    # labels = p1.labels
    print('start tsne')
    n_downsample = 500
    if len(labels) > n_downsample:
        # idx = np.random.randint(len(labels), size=900)
        np.random.seed(2357)
        idx = np.random.choice(a=np.arange(0, len(labels)), size=1000, replace=False, p=None)
        print('len idx', len(idx))
        super_labels = np.asarray(super_labels)[idx]
        labels = list(np.asarray(labels)[idx])
        true_label = list(np.asarray(true_label[idx]))
        sc_pt_markov = list(np.asarray(p1.single_cell_pt_markov[idx]))
        graph = p0.knngraph_visual(adata_counts.obsm['X_pca'][idx, :], downsampled=True)
        # embedding = p0.run_umap_hnsw(adata_counts.obsm['X_pca'][idx, :], graph)
        embedding = adata_counts.obsm['X_pca'][idx,
                    0:2]  # umap.UMAP().fit_transform(adata_counts.obsm['X_pca'][idx, 0:5])
        # embedding = TSNE().fit_transform(adata_counts.obsm['X_pca'][idx, :])
        print('tsne downsampled size', embedding.shape)
    else:
        embedding = TSNE().fit_transform(pc)  # (adata_counts.obsm['X_pca'])
        print('tsne input size', adata_counts.obsm['X_pca'].shape)
        # embedding = umap.UMAP().fit_transform(adata_counts.obsm['X_pca'])
        idx = np.random.randint(len(labels), size=len(labels))
    print('end tsne')

    knn_hnsw, ci_list = sc_loc_ofsuperCluster_embeddedspace(embedding, p0, p1, idx)
    print('super terminal and sub terminal', p0.super_terminal_cells, p1.terminal_clusters)
    draw_trajectory_gams(embedding, ci_list, labels, super_labels, super_edges,
                         p1.x_lazy, p1.alpha_teleport, sc_pt_markov, true_label, knn=p0.knn,
                         final_super_terminal=p1.revised_super_terminal_clusters,
                         sub_terminal_clusters=p1.terminal_clusters,
                         title_str='Hitting times: Markov Simulation on biased edges', ncomp=ncomps)
    plt.show()
    '''
    draw_trajectory_dimred(embedding, ci_list, labels, super_labels, super_edges,
                           p1.x_lazy, p1.alpha_teleport, sc_pt_markov, true_label, knn=p0.knn,
                           final_super_terminal=p0.terminal_clusters,
                           title_str='Hitting times: Markov Simulation on biased edges', ncomp=ncomps)
    '''
    plt.show()

    num_group = len(set(true_label))
    line = np.linspace(0, 1, num_group)

    f, (ax1, ax3) = plt.subplots(1, 2, sharey=True)

    for color, group in zip(line, set(true_label)):
        where = np.where(np.asarray(true_label) == group)[0]

        ax1.scatter(embedding[where, 0], embedding[where, 1], label=group,
                    c=np.asarray(plt.cm.jet(color)).reshape(-1, 4))
    ax1.legend(fontsize=6)
    ax1.set_title('true labels')

    ax3.set_title("Markov Sim PT ncomps:" + str(pc.shape[1]) + '. knn:' + str(knn))
    ax3.scatter(embedding[:, 0], embedding[:, 1], c=sc_pt_markov, cmap='viridis_r')
    plt.show()
    df_subset = pd.DataFrame(adata_counts.obsm['X_pca'][:, 0:3], columns=['Gene0', 'Gene1', 'Gene2'])
    for gene_i in ['Gene0', 'Gene1', 'Gene2']:
        subset_ = df_subset[gene_i].values
        print(subset_.shape)
        # print('shapes of magic_ad 1 and 2', magic_ad.shape,subset_.shape)
        # p1.get_gene_expression(magic_ad,title_gene = gene_name_dict[gene_name])
        p1.get_gene_expression(subset_, title_gene=gene_i + 'VIA MAGIC')

    draw_sc_evolution_trajectory_dijkstra(p1, embedding, knn_hnsw, p0.full_graph_shortpath, idx,
                                          adata_counts.obsm['X_pca'][:, 0:ncomps])

    plt.show()


def main_Bcell(ncomps, knn, random_seed):
    print('ncomp, knn, random seed', ncomps, knn, random_seed)

    # https://github.com/STATegraData/STATegraData
    def run_zheng(adata, min_counts=3, n_top_genes=500, do_HVG=True):
        sc.pp.filter_genes(adata, min_counts=min_counts)
        # sc.pp.filter_genes(adata, min_cells=3)# only consider genes with more than 1 count
        '''
        sc.pp.normalize_per_cell(  # normalize with total UMI count per cell
            adata, key_n_counts='n_counts_all')
        '''
        sc.pp.normalize_total(adata, target_sum=1e4)
        if do_HVG == True:
            sc.pp.log1p(adata)
            '''
            filter_result = sc.pp.filter_genes_dispersion(  # select highly-variable genes
            adata.X, flavor='cell_ranger', n_top_genes=n_top_genes, log=False )
            adata = adata[:, filter_result.gene_subset]  # subset the genes
            '''
            sc.pp.highly_variable_genes(adata, n_top_genes=n_top_genes, min_mean=0.0125, max_mean=3,
                                        min_disp=0.5)  # this function expects logarithmized data
            print('len hvg ', sum(adata.var.highly_variable))
            adata = adata[:, adata.var.highly_variable]
        sc.pp.normalize_per_cell(adata)  # renormalize after filtering
        # if do_log: sc.pp.log1p(adata)  # log transform: adata.X = log(adata.X + 1)
        if do_HVG == False: sc.pp.log1p(adata)
        sc.pp.scale(adata, max_value=10)  # scale to unit variance and shift to zero mean
        return adata

    def run_paga_func_Bcell(adata_counts1, ncomps, knn, embedding):
        # print('npwhere',np.where(np.asarray(adata_counts.obs['group_id']) == '0')[0][0])
        adata_counts = adata_counts1.copy()
        sc.tl.pca(adata_counts, svd_solver='arpack', n_comps=ncomps)
        adata_counts.uns['iroot'] = 33  # np.where(np.asarray(adata_counts.obs['group_id']) == '0')[0][0]

        sc.pp.neighbors(adata_counts, n_neighbors=knn, n_pcs=ncomps)  # 4
        sc.tl.draw_graph(adata_counts)
        sc.pl.draw_graph(adata_counts, color='group_id', legend_loc='on data')  # force-directed layout
        start_dfmap = time.time()
        sc.tl.diffmap(adata_counts, n_comps=ncomps)
        print('time taken to get diffmap given knn', time.time() - start_dfmap)
        sc.pp.neighbors(adata_counts, n_neighbors=knn, use_rep='X_diffmap')  # 4
        sc.tl.draw_graph(adata_counts)
        sc.pl.draw_graph(adata_counts, color='group_id', legend_loc='on data')
        sc.tl.leiden(adata_counts, resolution=1.0)
        sc.tl.paga(adata_counts, groups='leiden')
        # sc.pl.paga(adata_counts, color=['louvain','group_id'])

        sc.tl.dpt(adata_counts, n_dcs=ncomps)
        sc.pl.paga(adata_counts, color=['leiden', 'group_id', 'dpt_pseudotime'],
                   title=['leiden (knn:' + str(knn) + ' ncomps:' + str(ncomps) + ')',
                          'group_id (ncomps:' + str(ncomps) + ')', 'pseudotime (ncomps:' + str(ncomps) + ')'])
        sc.pl.draw_graph(adata_counts, color='dpt_pseudotime', legend_loc='on data')
        print('dpt format', adata_counts.obs['dpt_pseudotime'])
        plt.scatter(embedding[:, 0], embedding[:, 1], c=adata_counts.obs['dpt_pseudotime'].values, cmap='viridis')
        plt.title('PAGA DPT')
        plt.show()

    def run_palantir_func_Bcell(ad1, ncomps, knn, tsne_X, true_label):
        ad = ad1.copy()
        tsne = pd.DataFrame(tsne_X, index=ad.obs_names, columns=['x', 'y'])
        norm_df_pal = pd.DataFrame(ad.X)
        new = ['c' + str(i) for i in norm_df_pal.index]
        norm_df_pal.columns = [i for i in ad.var_names]
        # print('norm df', norm_df_pal)

        norm_df_pal.index = new
        pca_projections, _ = palantir.utils.run_pca(norm_df_pal, n_components=ncomps)

        sc.tl.pca(ad, svd_solver='arpack')
        dm_res = palantir.utils.run_diffusion_maps(pca_projections, n_components=ncomps, knn=knn)

        ms_data = palantir.utils.determine_multiscale_space(dm_res)  # n_eigs is determined using eigengap
        print('ms data shape: determined using eigengap', ms_data.shape)
        # tsne =  pd.DataFrame(tsnem)#palantir.utils.run_tsne(ms_data)
        tsne.index = new
        # print(type(tsne))
        str_true_label = pd.Series(true_label, index=norm_df_pal.index)

        palantir.plot.plot_cell_clusters(tsne, str_true_label)

        start_cell = 'c42'  # '#C108 for M12 connected' #M8n1000d1000 start - c107 #c1001 for bifurc n2000d1000 #disconnected n1000 c108, "C1 for M10 connected" # c10 for bifurcating_m4_n2000d1000

        pr_res = palantir.core.run_palantir(ms_data, early_cell=start_cell, num_waypoints=1200, knn=knn)
        palantir.plot.plot_palantir_results(pr_res, tsne, n_knn=knn, n_comps=ncomps)
        imp_df = palantir.utils.run_magic_imputation(norm_df_pal, dm_res)
        Bcell_marker_gene_list = ['Igll1', 'Myc', 'Ldha', 'Foxo1', 'Lig4']  # , 'Slc7a5']#,'Slc7a5']#,'Sp7','Zfp629']
        gene_trends = palantir.presults.compute_gene_trends(pr_res, imp_df.loc[:, Bcell_marker_gene_list])
        palantir.plot.plot_gene_trends(gene_trends)
        plt.show()

    def find_time(s):
        start = s.find("Ik") + len("Ik")
        end = s.find("h")
        return int(s[start:end])

    def find_cellID(s):
        start = s.find("h") + len("h")
        end = s.find("_")
        return s[start:end]

    # diff = pd.read_excel('/home/shobi/Downloads/journal_bgenes.xlsx', sep='\t')
    # is_diff = diff['CONSENSUS_DE']==1
    # diff = diff[is_diff]

    # print('shape dff', diff.shape)
    # diff_list = diff['MGI_Symbol'].values.tolist()
    # diff_list = [i for i in diff_list if isinstance(i, str) ]

    Bcell = pd.read_csv('/home/shobi/Trajectory/Datasets/Bcell/genes_count_table.txt', sep='\t')
    gene_name = pd.read_csv('/home/shobi/Trajectory/Datasets/Bcell/genes_attr_table.txt', sep='\t')

    Bcell_columns = [i for i in Bcell.columns]
    adata_counts = sc.AnnData(Bcell.values[:, 1:].T)
    Bcell_columns.remove('tracking_id')

    print(gene_name.shape, gene_name.columns)
    Bcell['gene_short_name'] = gene_name['gene_short_name']
    adata_counts.var_names = gene_name['gene_short_name']
    adata_counts.obs['TimeCellID'] = Bcell_columns

    time_list = [find_time(s) for s in Bcell_columns]
    # for ii, jj in enumerate(time_list):
    # print(ii, jj)
    print('time list set', set(time_list))
    adata_counts.obs['TimeStamp'] = [str(tt) for tt in time_list]
    # for i in Bcell_columns:
    #    print(i)
    # adata_counts.var_names_make_unique()

    ID_list = [find_cellID(s) for s in Bcell_columns]
    adata_counts.obs['group_id'] = [str(i) for i in time_list]
    ID_dict = {}
    color_dict = {}
    for j, i in enumerate(list(set(ID_list))):
        ID_dict.update({i: j})
    for j, i in enumerate(list(set(time_list))):
        color_dict.update({i: j})

    print('shape of raw data', adata_counts.shape)
    # sc.pp.filter_genes(adata_counts, min_counts=3)
    adata_counts_unfiltered = adata_counts.copy()

    Bcell_marker_gene_list = ['Myc', 'Igll1', 'Slc7a5', 'Ldha', 'Foxo1', 'Lig4']

    small_large_gene_list = ['Kit', 'Pcna', 'Ptprc', 'Il2ra', 'Vpreb1', 'Cd24a', 'Igll1', 'Cd79a', 'Cd79b', 'Mme',
                             'Spn']
    list_var_names = [s for s in adata_counts_unfiltered.var_names]
    matching = [s for s in list_var_names if "IgG" in s]
    print('matching', matching)
    for gene_name in Bcell_marker_gene_list:
        print('gene name', gene_name)
        loc_gata = np.where(np.asarray(adata_counts_unfiltered.var_names) == gene_name)[0][0]
    for gene_name in small_large_gene_list:
        print('looking at small-big list')
        print('gene name', gene_name)
        loc_gata = np.where(np.asarray(adata_counts_unfiltered.var_names) == gene_name)[0][0]
    # diff_list = [i for i in diff_list if i in list_var_names] #based on paper STable1 https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.2006506#pbio.2006506.s007
    # adata_counts = adata_counts[:,diff_list] #if using these, then set do-HVG to False
    print('adata counts difflisted', adata_counts.shape)
    adata_counts = run_zheng(adata_counts, n_top_genes=5000, min_counts=30, do_HVG=True)  # 5000 for better ordering
    print('adata counts shape', adata_counts.shape)
    # sc.pp.recipe_zheng17(adata_counts)

    # (ncomp=50, knn=20 gives nice results. use 10PCs for visualizing)

    marker_genes = {"small": ['Rag2', 'Rag1', 'Pcna', 'Myc', 'Ccnd2', 'Cdkn1a', 'Smad4', 'Smad3', 'Cdkn2a'],
                    # B220 = Ptprc, PCNA negative for non cycling
                    "large": ['Ighm', 'Kit', 'Ptprc', 'Cd19', 'Il2ra', 'Vpreb1', 'Cd24a', 'Igll1', 'Cd79a', 'Cd79b'],
                    "Pre-B2": ['Mme', 'Spn']}  # 'Cd19','Cxcl13',,'Kit'

    print('make the p0 matrix plot')
    mplot_adata = adata_counts_unfiltered.copy()
    mplot_adata = run_zheng(mplot_adata, n_top_genes=25000, min_counts=1, do_HVG=False)
    # mplot_adata.X[mplot_adata.X>10] =10
    # mplot_adata.X[mplot_adata.X< -1] = -1
    sc.pl.matrixplot(mplot_adata, marker_genes, groupby='TimeStamp', dendrogram=True)

    sc.tl.pca(adata_counts, svd_solver='arpack', n_comps=200)  # ncomps
    # sc.pl.pca_variance_ratio(adata_counts, log=True)

    jet = cm.get_cmap('viridis', len(set(time_list)))
    cmap_ = jet(range(len(set(time_list))))

    jet2 = cm.get_cmap('jet', len(set(ID_list)))
    cmap2_ = jet2(range(len(set(ID_list))))

    # color_dict = {"0": [0], "2": [1], "6": [2], "12": [3], "18": [4], "24": [5]}
    # sc.pl.heatmap(mplot_adata, var_names  = small_large_gene_list,groupby = 'TimeStamp', dendrogram = True)
    embedding = umap.UMAP(random_state=42, n_neighbors=15, init='random').fit_transform(
        adata_counts.obsm['X_pca'][:, 0:5])
    df_umap = pd.DataFrame(embedding)
    df_umap.to_csv('/home/shobi/Trajectory/Datasets/Bcell/Bcell_umap.csv')

    f, (ax1, ax2, ax3, ax4) = plt.subplots(1, 4, sharey=True)
    for i in list(set(time_list)):
        loc = np.where(np.asarray(time_list) == i)[0]
        ax4.scatter(embedding[loc, 0], embedding[loc, 1], c=cmap_[color_dict[i]], alpha=1, label=str(i))
        if i == 0:
            for xx in range(len(loc)):
                poss = loc[xx]
                ax4.text(embedding[poss, 0], embedding[poss, 1], 'c' + str(xx))

    ax4.legend()

    ax1.scatter(embedding[:, 0], embedding[:, 1], c=mplot_adata[:, 'Pcna'].X.flatten(), alpha=1)
    ax1.set_title('Pcna, cycling')
    ax2.scatter(embedding[:, 0], embedding[:, 1], c=mplot_adata[:, 'Vpreb1'].X.flatten(), alpha=1)
    ax2.set_title('Vpreb1')
    ax3.scatter(embedding[:, 0], embedding[:, 1], c=mplot_adata[:, 'Cd24a'].X.flatten(), alpha=1)
    ax3.set_title('Cd24a')

    # ax2.text(embedding[i, 0], embedding[i, 1], str(i))

    '''    
    for i, j in enumerate(list(set(ID_list))):
        loc = np.where(np.asarray(ID_list) == j)
        if 'r'in j: ax2.scatter(embedding[loc, 0], embedding[loc, 1], c=cmap2_[i], alpha=1, label=str(j), edgecolors = 'black' )
        else: ax2.scatter(embedding[loc, 0], embedding[loc, 1], c=cmap2_[i], alpha=1, label=str(j))
    '''
    # plt.show()

    true_label = time_list

    # run_paga_func_Bcell(adata_counts, ncomps, knn, embedding)

    # run_palantir_func_Bcell(adata_counts, ncomps, knn, embedding, true_label)

    print('input has shape', adata_counts.obsm['X_pca'].shape)
    input_via = adata_counts.obsm['X_pca'][:, 0:ncomps]

    df_input = pd.DataFrame(adata_counts.obsm['X_pca'][:, 0:200])
    df_annot = pd.DataFrame(['t' + str(i) for i in true_label])
    df_input.to_csv('/home/shobi/Trajectory/Datasets/Bcell/Bcell_200PC_5000HVG.csv')
    df_annot.to_csv('/home/shobi/Trajectory/Datasets/Bcell/Bcell_annots.csv')

    p0 = PARC(input_via, true_label, jac_std_global=0.15, dist_std_local=1, knn=knn,
              too_big_factor=0.3, dataset='bcell',
              pseudotime=True, path="/home/shobi/Trajectory/Datasets/" + 'bcell' + "/",
              root_user=42, preserve_disconnected=True, random_seed=random_seed,
              do_magic_bool=True)  # *.4#root_user = 34
    p0.run_PARC()
    super_labels = p0.labels

    '''
    umap_init_ = p0.graph_node_pos
    umap_init_ = np.asarray(umap_init_)
    umap_init = np.random.rand(len(super_labels),2)
    for clus_i in range(umap_init_.shape[0]):
        loc_clus_i = np.where(np.asarray(super_labels) == clus_i)[0]
        umap_init[loc_clus_i,0]=umap_init_[clus_i,0]
        umap_init[loc_clus_i, 1] = umap_init_[clus_i, 1]
    '''
    p = hnswlib.Index(space='l2', dim=adata_counts.obsm['X_pca'][:, 0:ncomps].shape[1])
    p.init_index(max_elements=adata_counts.obsm['X_pca'][:, 0:ncomps].shape[0], ef_construction=100, M=16)
    p.add_items(adata_counts.obsm['X_pca'][:, 0:ncomps])
    p.set_ef(30)
    tsi_list = []  # find the single-cell which is nearest to the average-location of a terminal cluster in PCA space (
    for tsi in p0.terminal_clusters:
        loc_i = np.where(np.asarray(p0.labels) == tsi)[0]
        val_pt = [p0.single_cell_pt_markov[i] for i in loc_i]
        th_pt = np.percentile(val_pt, 50)  # 50
        loc_i = [loc_i[i] for i in range(len(val_pt)) if val_pt[i] >= th_pt]
        temp = np.mean(adata_counts.obsm['X_pca'][:, 0:ncomps][loc_i], axis=0)
        labelsq, distances = p.knn_query(temp, k=1)
        print(labelsq[0])
        tsi_list.append(labelsq[0][0])

    p1 = PARC(adata_counts.obsm['X_pca'][:, 0:ncomps], true_label, jac_std_global=0.15, dist_std_local=1, knn=knn,
              too_big_factor=0.05,
              path="/home/shobi/Trajectory/Datasets/" + "bcell/", pseudotime=True,
              super_cluster_labels=super_labels, super_node_degree_list=p0.node_degree_list,
              super_terminal_cells=tsi_list, root_user=42,
              x_lazy=0.99, alpha_teleport=0.99, preserve_disconnected=True, dataset='bcell',
              super_terminal_clusters=p0.terminal_clusters, random_seed=random_seed)

    p1.run_PARC()
    labels = p1.labels
    super_edges = p0.edgelist

    # plot gene expression vs. pseudotime
    Bcell_marker_gene_list = ['Igll1']  # , 'Myc', 'Slc7a5', 'Ldha', 'Foxo1', 'Lig4','Sp7','Zfp629'] #irf4 down-up
    df_ = pd.DataFrame(adata_counts_unfiltered.X)
    df_.columns = [i for i in adata_counts_unfiltered.var_names]
    df_magic = p0.do_magic(df_, magic_steps=3, gene_list=Bcell_marker_gene_list)
    for gene_name in Bcell_marker_gene_list:
        # loc_gata = np.where(np.asarray(adata_counts_unfiltered.var_names) == gene_name)[0][0]
        subset_ = df_magic[gene_name].values

        p1.get_gene_expression(subset_, title_gene=gene_name + ' (VIA MAGIC)')

        # magic_ad = adata_counts_unfiltered.X[:, loc_gata]
        # p1.get_gene_expression(magic_ad, gene_name)

    n_downsample = 100
    if len(labels) > n_downsample:
        # idx = np.random.randint(len(labels), size=900)
        np.random.seed(2357)
        # idx = np.random.choice(a=np.arange(0, len(labels)), size=len(labels), replace=False, p=None)
        idx = np.arange(0, len(labels))
        super_labels = np.asarray(super_labels)[idx]
        labels = list(np.asarray(labels)[idx])
        true_label = list((np.asarray(true_label)[idx]))
        sc_pt_markov = list(np.asarray(p1.single_cell_pt_markov[idx]))
        # embedding = TSNE().fit_transform(adata_counts.obsm['X_pca'][idx, :])
        graph_embedding = p0.knngraph_visual(input_via[idx, 0:5], knn_umap=10, downsampled=True)
        embedding_hnsw = p0.run_umap_hnsw(input_via[idx, 0:5], graph_embedding)
        # embedding = embedding_hnsw
        # loc0 = np.where(np.asarray(true_label)==0)[0]
        # for item in loc0:
        # print(item, 'at', embedding[item,:])
        print('tsne downsampled size', embedding.shape)
    else:
        # embedding = TSNE().fit_transform(adata_counts.obsm['X_pca'][:,0:5])  # (adata_counts.obsm['X_pca'])
        print('tsne input size', adata_counts.obsm['X_pca'].shape)
        # embedding = umap.UMAP().fit_transform(adata_counts.obsm['X_pca'])
        idx = np.arange(0, len(labels))  # np.random.randint(len(labels), size=len(labels))
        sc_pt_markov = p1.single_cell_pt_markov

    # embedding = umap.UMAP(random_state=42, n_neighbors=15, init=umap_init).fit_transform(  adata_counts.obsm['X_pca'][:, 0:5])

    knn_hnsw, ci_list = sc_loc_ofsuperCluster_embeddedspace(embedding, p0, p1, idx)

    draw_trajectory_gams(embedding, ci_list, labels, super_labels, super_edges,
                         p1.x_lazy, p1.alpha_teleport, sc_pt_markov, true_label, knn=p0.knn,
                         final_super_terminal=p1.revised_super_terminal_clusters,
                         sub_terminal_clusters=p1.terminal_clusters,
                         title_str='Markov Hitting Times (Gams)', ncomp=ncomps)
    plt.show()
    '''
    draw_trajectory_dimred(embedding, ci_list, labels, super_labels, super_edges,
                           p1.x_lazy, p1.alpha_teleport, sc_pt_markov, true_label, knn=p0.knn,
                           final_super_terminal=p0.terminal_clusters,
                           title_str='Markov Hitting Times (polyfit)', ncomp=ncomps)
    plt.show()
    '''
    # draw_sc_evolution_trajectory_dijkstra(p1, embedding, knn_hnsw, p0.full_graph_shortpath, idx,  adata_counts.obsm['X_pca'][:, 0:ncomps])

    plt.show()


def main_iPSC(ncomps=100, knn=30, p0_random_seed=12, run_palantir_func=False):
    p0_random_seed = 42
    root = '2'
    type = 'NG'
    data = pd.read_csv('/home/shobi/Trajectory/Datasets/iPSC/NN_all_18markers.csv')
    print(data.head())
    print(data.shape)

    # data = data[data['day']!=0]
    true_label = data['day']
    data = data.drop(['day', 'Unnamed: 0'], axis=1)
    # data = data.drop(['Unnamed: 0'], axis=1)
    raw = data.values
    # raw = raw/5
    raw = np.arcsinh(raw)
    print(data.shape)

    adata = sc.AnnData(raw)
    adata.var_names = data.columns
    print(adata.shape)

    true_label_int = [i for i in true_label]
    adata.obs['day'] = ['0' + str(i) if i < 10 else str(i) for i in true_label_int]
    true_label_str = ['0' + str(i) if i < 10 else str(i) for i in
                      true_label]  # the way find_root works is to match any part of root-user to majority truth

    print(adata.obs['day'])
    sc.pp.scale(adata, max_value=5)
    # ncomps = 30

    # sc.tl.pca(adata, svd_solver='arpack', n_comps=ncomps)
    idx = np.random.choice(a=np.arange(0, len(true_label)), size=20000, replace=False, p=None)  # len(true_label)

    true_label_str = list(np.asarray(true_label_str)[idx])
    true_label_int = list(np.asarray(true_label_int)[idx])

    p0 = PARC(adata.X[idx, :], true_label_int, jac_std_global=0.15, dist_std_local=1, knn=knn,
              too_big_factor=0.4,
              pseudotime=True, path="/home/shobi/Trajectory/Datasets/iPSC/",
              root_user=root, dataset='iPSC', preserve_disconnected=True, random_seed=p0_random_seed,
              do_magic_bool=True, is_coarse=True)  # *.4 root=1,
    p0.run_PARC()
    marker_genes = ['Oct4', 'Sox2', 'Klf4', 'c-Myc', 'Nanog', 'GFP', 'Lin28', 'SSEA1', 'EpCAM', 'CD54', 'CD73', 'Thy1',
                    'MEFSK4', 'CD140a', 'CD24', 'CD44', 'H3K9ac', 'Ki67']
    adata_idx = adata[idx]
    adata_idx.obs['parc0'] = [str(i) for i in p0.labels]
    sc.pl.matrixplot(adata_idx, marker_genes, groupby='parc0', dendrogram=True)

    p = hnswlib.Index(space='l2', dim=adata.X[idx, :].shape[1])
    p.init_index(max_elements=adata.X[idx, :].shape[0], ef_construction=100, M=16)
    p.add_items(adata.X[idx, :])
    p.set_ef(30)
    tsi_list = []  # find the single-cell which is nearest to the average-location of a terminal cluster in PCA space (
    for tsi in p0.terminal_clusters:
        loc_i = np.where(np.asarray(p0.labels) == tsi)[0]
        val_pt = [p0.single_cell_pt_markov[i] for i in loc_i]
        th_pt = np.percentile(val_pt, 50)  # 50
        loc_i = [loc_i[i] for i in range(len(val_pt)) if val_pt[i] >= th_pt]
        temp = np.mean(adata.X[idx, :][loc_i], axis=0)
        labelsq, distances = p.knn_query(temp, k=1)
        print(labelsq[0])
        tsi_list.append(labelsq[0][0])
    super_labels = p0.labels
    p1 = PARC(adata.X[idx, :], true_label_int, jac_std_global=0.15, dist_std_local=1, knn=knn,
              too_big_factor=0.05,
              path="/home/shobi/Trajectory/Datasets/" + "bcell/", pseudotime=True,
              super_cluster_labels=super_labels, super_node_degree_list=p0.node_degree_list,
              super_terminal_cells=tsi_list, root_user=root,
              x_lazy=0.99, alpha_teleport=0.99, preserve_disconnected=True, dataset='iPSC',
              super_terminal_clusters=p0.terminal_clusters, random_seed=p0_random_seed)

    p1.run_PARC()
    adata_idx.obs['parc1'] = [str(i) for i in p1.labels]
    sc.pl.matrixplot(adata_idx, marker_genes, groupby='parc1', dendrogram=True)
    labels = p1.labels

    # X = adata.obsm['X_pca'][:,0:2]
    # print(X.shape)
    udata = adata.X[idx, :][0:10000, :]
    c_pt = p1.single_cell_pt_markov[0:10000]
    u_truelabel = true_label_int[0:10000]

    U = umap.UMAP().fit_transform(udata)
    # U = umap.UMAP().fit_transform(adata.obsm['X_pca'][idx, 0:ncomps])
    U_df = pd.DataFrame(U, columns=['x', 'y'])
    # U_df.to_csv('/home/shobi/Trajectory/Datasets/iPSC/FI_all_umap.csv')

    f, (ax1, ax2) = plt.subplots(1, 2, sharey=True)
    ax1.scatter(U[:, 0], U[:, 1], c=u_truelabel, cmap='jet', s=4, alpha=0.7)
    ax2.scatter(U[:, 0], U[:, 1], c=c_pt, cmap='jet', s=4, alpha=0.7)
    plt.title(str(len(idx)) + 'cells ' + type)
    plt.show()


def plot_EB():
    df_groupby_p1 = pd.read_csv(
        '/home/shobi/Trajectory/Datasets/EB_Phate/df_groupbyParc1_knn20_pc100_seed20_allgenes.csv')

    path_clusters = [43, 38, 42, 56, 7,
                     3]  # NC[43,41,16,2,3,6]#SMP[43,41,16,14,11,18]#C[43,41,16,14,12,15]#NS3[43,38,42,56,7,3]
    target = "NS 3"  # 'NC 6' #'SMP 18'#' Cardiac 15'
    marker_genes_dict = {'Hermang': ['TAL1', 'HOXB4', 'SOX17', 'CD34', 'PECAM1'],
                         'NP': ['NES', 'MAP2'], 'NS': ['LHX2', 'NR2F1', 'DMRT3', 'LMX1A',
                                                       # 'KLF7', 'ISL1', 'DLX1', 'ONECUT1', 'ONECUT2', 'OLIG1','PAX6', 'ZBTB16','NPAS1', 'SOX1'
                                                       'NKX2-8', 'EN2'], 'NC': ['PAX3', 'FOXD3', 'SOX9', 'SOX10'],
                         'PostEn': ['CDX2', 'ASCL2', 'KLF5', 'NKX2-1'],
                         'EN': ['ARID3A', 'GATA3', 'SATB1', 'SOX15', 'SOX17', 'FOXA2'],
                         'Pre-NE': ['POU5F1', 'OTX2'], 'SMP': ['TBX18', 'SIX2', 'TBX15', 'PDGFRA'],
                         'Cardiac': ['TNNT2', 'HAND1', 'F3', 'CD82', 'LIFR'],
                         'EpiCard': ['WT1', 'TBX5', 'HOXD9', 'MYC', 'LOX'],
                         'PS/ME': ['T', 'EOMES', 'MIXL1', 'CER1', 'SATB1'],
                         'NE': ['GBX2', 'GLI3', 'LHX2', 'LHX5', 'SIX3', 'SIX6'],
                         # 'OLIG3','HOXD1', 'ZIC2', 'ZIC5','HOXA2','HOXB2'
                         'ESC': ['NANOG', 'POU5F1'], 'Pre-NE': ['POU5F1', 'OTX2'], 'Lat-ME': ['TBX5', 'HOXD9', 'MYC']}
    relevant_genes = []
    relevant_keys = ['ESC', 'Pre-NE', 'NE', 'NP',
                     'NS']  # NC['ESC', 'Pre-NE', 'NE', 'NC']#SMP['ESC','PS/ME','Lat-ME','SMP']#NS['ESC', 'Pre-NE', 'NE', 'NP', 'NS']
    dict_subset = {key: value for key, value in marker_genes_dict.items() if key in relevant_keys}
    print('dict subset', dict_subset)
    for key in relevant_keys:
        relevant_genes.append(marker_genes_dict[key])

    relevant_genes = [item for sublist in relevant_genes for item in sublist]

    print(relevant_genes)
    df_groupby_p1 = df_groupby_p1.set_index('parc1')
    df_groupby_p1 = df_groupby_p1.loc[path_clusters]
    df_groupby_p1 = df_groupby_p1[relevant_genes]

    df_groupby_p1 = df_groupby_p1.transpose()

    # print( df_groupby_p1.head)

    # print(df_groupby_p1)
    ax = sns.heatmap(df_groupby_p1, vmin=-1, vmax=1, yticklabels=True)

    ax.set_title('target ' + str(target))
    plt.show()

    # df_groupby_p1 = pd.concat([df_groupby_p1,df_groupby_p1])
    # adata = sc.AnnData(df_groupby_p1)
    # adata.var_names = df_groupby_p1.columns
    # print(adata.var_names)
    # adata.obs['parc1'] = ['43','38','42','56','7','3','43','38','42','56','7','3']
    # print(adata.obs['parc1'])
    # sc.pl.matrixplot(adata, dict_subset, groupby='parc1', vmax=1, vmin=-1, dendrogram=False)


def main_EB(ncomps=100, knn=20, p0_random_seed=21):
    marker_genes_dict0 = {'Hermang': ['TAL1', 'HOXB4', 'SOX17', 'CD34', 'PECAM1'],
                          'NS': ['KLF7', 'ISL1', 'DLX1', 'ONECUT1', 'ONECUT2', 'OLIG1', 'NPAS1', 'LHX2', 'NR2F1',
                                 'NPAS1', 'DMRT3', 'LMX1A', 'NKX2-8', 'EN2', 'SOX1', 'PAX6', 'ZBTB16'],
                          'NC': ['PAX3', 'FOXD3', 'SOX9', 'SOX10'],
                          'EN': ['ARID3A', 'GATA3', 'SATB1', 'SOX15', 'SOX17', 'FOXA2'],
                          'PostEn': ['CDX2', 'ASCL2', 'KLF5', 'NKX2-1'], 'ESC': ['NANOG', 'POU5F1', 'OTX2'],
                          'Pre-NE': ['GBX2', 'OLIG3', 'HOXD1', 'ZIC2', 'ZIC5', 'HOXA2', 'HOXB2'],
                          'SMP': ['TBX18', 'SIX2', 'TBX15', 'PDGFRA'],
                          'Cardiac': ['TNNT2', 'HAND1', 'F3', 'CD82', 'LIFR'], 'EpiCard': ['WT1'], 'ME': ['T'],
                          'NE': ['GBX2', 'ZIC2', 'ZIC5', 'GLI3', 'LHX2', 'LHX5', 'SIX3', 'SIX6']}

    marker_genes_dict = {'Hermang': ['TAL1', 'HOXB4', 'SOX17', 'CD34', 'PECAM1'],
                         'NP': ['NES', 'MAP2'],
                         'NS': ['KLF7', 'ISL1', 'DLX1', 'ONECUT1', 'ONECUT2', 'OLIG1', 'NPAS1', 'LHX2', 'NR2F1',
                                'NPAS1', 'DMRT3', 'LMX1A',
                                'NKX2-8', 'EN2', 'SOX1', 'PAX6', 'ZBTB16'], 'NC': ['PAX3', 'FOXD3', 'SOX9', 'SOX10'],
                         'PostEn': ['CDX2', 'ASCL2', 'KLF5', 'NKX2-1'],
                         'EN': ['ARID3A', 'GATA3', 'SATB1', 'SOX15', 'SOX17', 'FOXA2'], 'Pre-NE': ['POU5F1', 'OTX2'],
                         'SMP': ['TBX18', 'SIX2', 'TBX15', 'PDGFRA'],
                         'Cardiac': ['TNNT2', 'HAND1', 'F3', 'CD82', 'LIFR'],
                         'EpiCard': ['WT1', 'TBX5', 'HOXD9', 'MYC', 'LOX'],
                         'PS/ME': ['T', 'EOMES', 'MIXL1', 'CER1', 'SATB1'],
                         'NE': ['GBX2', 'OLIG3', 'HOXD1', 'ZIC2', 'ZIC5', 'GLI3', 'LHX2', 'LHX5', 'SIX3', 'SIX6',
                                'HOXA2', 'HOXB2'], 'ESC': ['NANOG', 'POU5F1', 'OTX2'], 'Pre-NE': ['POU5F1', 'OTX2']}
    marker_genes_list = []
    for key in marker_genes_dict:
        for item in marker_genes_dict[key]:
            marker_genes_list.append(item)

    # 'GATA5, GATA6',
    p0_too_big = 0.3
    p1_too_big = 0.05
    # 20

    n_var_genes = 'no filtering for HVG'  # 15000
    print('ncomps, knn, n_var_genes, p0big, p1big, randomseed, time', ncomps, knn, n_var_genes, p0_too_big, p1_too_big,
          p0_random_seed, time.ctime())
    # data = pd.read_csv('/home/shobi/Trajectory/Datasets/EB_Phate/EBT_counts_nosqrt_noNorm.csv')

    # data = data.drop(['Unnamed: 0'], axis=1)
    # print(data.shape, data)
    TI_pcs = pd.read_csv('/home/shobi/Trajectory/Datasets/EB_Phate/PCA_TI_200_TuesAM.csv')
    TI_pcs = TI_pcs.values[:, 1:]

    umap_pcs = pd.read_csv('/home/shobi/Trajectory/Datasets/EB_Phate/PCA_umap_200_TuesAM.csv')
    umap_pcs = umap_pcs.values[:, 1:]
    # print('TI PC shape', TI_pcs.shape)
    from scipy.io import loadmat
    annots = loadmat(
        '/home/shobi/Trajectory/Datasets/EB_Phate/EBdata.mat')  # has been filtered but not yet normed (by library s
    data = annots['data'].toarray()  # (16825, 17580) (cells and genes have been filtered)
    print('data min max', np.max(data), np.min(data), data[1, 0:20], data[5, 250:270], data[1000, 15000:15050])
    loc_ = np.where((data < 1) & (data > 0))
    temp = data[(data < 1) & (data > 0)]
    print('temp non int', temp)

    time_labels = annots['cells'].flatten().tolist()

    dict_labels = {'Day 00-03': 0, 'Day 06-09': 2, 'Day 12-15': 4, 'Day 18-21': 6, 'Day 24-27': 8}

    # print(annots.keys())  # (['__header__', '__version__', '__globals__', 'EBgenes_name', 'cells', 'data'])
    gene_names_raw = annots['EBgenes_name']  # (17580, 1) genes
    print(data)
    print(data.shape)

    print('data', data)
    adata = sc.AnnData(data)
    # time_labels = pd.read_csv('/home/shobi/Trajectory/Datasets/EB_Phate/labels_1.csv')
    # time_labels = time_labels.drop(['Unnamed: 0'], axis=1)
    # time_labels = time_labels['time']
    # adata.obs['time'] = [str(i) for i in time_labels]
    print(adata)
    gene_names = []
    for i in gene_names_raw:
        gene_names.append(i[0][0])
    adata.var_names = gene_names
    adata.obs['time'] = [str(i) for i in time_labels]

    # filter_result = sc.pp.filter_genes_dispersion(adata.X, flavor='cell_ranger', n_top_genes=5000, log=False) #dont take log
    adata_umap = adata.copy()
    # adata = adata[:, filter_result.gene_subset]  # subset the genes
    # sc.pp.normalize_per_cell(adata, min_counts=2)  # renormalize after filtering
    print('data max min BEFORE NORM', np.max(adata.X), np.min(adata.X), adata.X[1, 0:20])
    rowsums = adata.X.sum(axis=1)
    # adata.X = adata.X / rowsums[:, np.newaxis]
    # adata.X = sc.pp.normalize_total(adata, exclude_highly_expressed=True, max_fraction=0.05, inplace=False)['X']  #normalize after filtering
    adata.X = sc.pp.normalize_total(adata, inplace=False)['X']  # normalize after filtering
    print('data max min after NORM', np.max(adata.X), np.min(adata.X), adata.X[1, 0:20])
    adata.X = np.sqrt(adata.X)  # follow Phate paper which doesnt take log1() but instead does sqrt() transformation
    adata_umap.X = np.sqrt(adata_umap.X)
    print('data max min after SQRT', np.max(adata.X), np.min(adata.X), adata.X[1, 0:20])
    # sc.pp.log1p(adata)  # log transform: adata.X = log(adata.X + 1)
    scale = True
    if scale == True:
        print('pp scaled')
        # sc.pp.scale(adata)
        adata.X = (adata.X - np.mean(adata.X, axis=0)) / np.std(adata.X, axis=0)
        sc.pp.scale(adata_umap)
        print('data max min after SCALED', np.max(adata.X), np.min(adata.X))
    else:

        print('not pp scaled')

    print('sqrt transformed')
    # sc.pp.recipe_zheng17(adata, n_top_genes=15000) #expects non-log data
    # g = sc.tl.rank_genes_groups(adata, groupby='time', use_raw=True, n_genes=10)#method='t-test_overestim_var'
    # sc.pl.rank_genes_groups_heatmap(adata, n_genes=3, standard_scale='var')

    print(adata.X)

    '''
    pcs = pd.read_csv('/home/shobi/Trajectory/Datasets/EB_Phate/umap_200_matlab.csv')
    pcs = pcs.drop(['Unnamed: 0'], axis=1)
    pcs = pcs.values
    print(time.ctime())
    ncomps = 50
    input_data =pcs[:, 0:ncomps]
    '''

    print('p0_toobig, p1_toobig, p0randomseed', p0_too_big, p1_too_big, p0_random_seed)
    print('do pca')
    # sc.tl.pca(adata, svd_solver='arpack', n_comps=200, random_state = 0)
    # sc.tl.pca(adata_umap, svd_solver='arpack', n_comps=200)
    # df_pca_TI_200 = pd.DataFrame(adata.obsm['X_pca'])
    # df_pca_TI_200.to_csv('/home/shobi/Trajectory/Datasets/EB_Phate/PCA_TI_200_TuesAM.csv')

    # df_pca_umap_200 = pd.DataFrame(adata_umap.obsm['X_pca'])
    # df_pca_umap_200.to_csv('/home/shobi/Trajectory/Datasets/EB_Phate/PCA_umap_200_TuesAM.csv')
    adata.obsm['X_pca'] = TI_pcs
    adata_umap.obsm['X_pca'] = umap_pcs

    input_data = adata.obsm['X_pca'][:, 0:ncomps]
    '''
    #plot genes vs clusters for each trajectory

    df_plot_gene = pd.DataFrame(adata.X, columns=[i for i in adata.var_names])
    df_plot_gene = df_plot_gene[marker_genes_list]

    previous_p1_labels = pd.read_csv('/home/shobi/Trajectory/Datasets/EB_Phate/df_labels_knn20_pc100_seed20.csv')

    title_str = 'Terminal state 27 (Cardiac)'
    gene_groups = ['ESC', 'PS/ME','EN','Cardiac']
    clusters = [43,41,16,14,12,27]
    '''
    import umap
    u_knn = 15
    repulsion_strength = 1
    n_pcs = 10
    print('knn and repel', u_knn, repulsion_strength)
    U = pd.read_csv('/home/shobi/Trajectory/Datasets/EB_Phate/umap_pc10_knn15.csv')
    U = U.values[:, 1:]

    # U = umap.UMAP(n_neighbors=u_knn, random_state=1, repulsion_strength=repulsion_strength).fit_transform(adata_umap.obsm['X_pca'][:, 0:n_pcs])
    print('start palantir', time.ctime())
    # run_palantir_EB(adata, knn=knn, ncomps=ncomps, tsne=U, str_true_label=[str(i) for i in time_labels])
    print('end palantir', time.ctime())
    # df_U = pd.DataFrame(U)
    # df_U.to_csv('/home/shobi/Trajectory/Datasets/EB_Phate/umap_pc10_knn15.csv')

    print('do p0')
    p0 = PARC(input_data, time_labels, jac_std_global=0.15, dist_std_local=1, knn=knn,
              too_big_factor=p0_too_big,
              pseudotime=True, path="/home/shobi/Trajectory/Datasets/mESC/",
              root_user=1, dataset='EB', random_seed=p0_random_seed,
              do_magic_bool=True, is_coarse=True, preserve_disconnected=True)  # *.4 root=1,
    p0.run_PARC()
    super_labels = p0.labels
    p0_labels_df = pd.DataFrame(super_labels, columns=['p0_labels'])
    p0_labels_df.to_csv('/home/shobi/Trajectory/Datasets/EB_Phate/p0_labels.csv')
    adata.obs['parc0'] = [str(i) for i in super_labels]
    '''
    df_temp1 = pd.DataFrame(adata.X, columns = [i for i in adata.var_names])
    df_temp1 = df_temp1[marker_genes_list]
    df_temp1['parc0']=[str(i) for i in super_labels]
    df_temp1 = df_temp1.groupby('parc0').mean()
    '''
    # sns.clustermap(df_temp1, vmin=-1, vmax=1,xticklabels=True, yticklabels=True, row_cluster= False, col_cluster=True)

    # sc.pl.matrixplot(adata, marker_genes_dict, groupby='parc0', vmax=1, vmin =-1, dendrogram=True)
    '''
    sc.tl.rank_genes_groups(adata, groupby='parc0', use_raw=True,
                            method='t-test_overestim_var', n_genes=5)  # compute differential expression
    sc.pl.rank_genes_groups_heatmap(adata, groupby='parc0',vmin=-3, vmax=3)  # plot the result
    '''

    p = hnswlib.Index(space='l2', dim=input_data.shape[1])
    p.init_index(max_elements=input_data.shape[0], ef_construction=100, M=16)
    p.add_items(input_data)
    p.set_ef(30)
    tsi_list = []  # find the single-cell which is nearest to the average-location of a terminal cluster in PCA space (
    for tsi in p0.terminal_clusters:
        loc_i = np.where(np.asarray(p0.labels) == tsi)[0]
        val_pt = [p0.single_cell_pt_markov[i] for i in loc_i]
        th_pt = np.percentile(val_pt, 50)  # 50
        loc_i = [loc_i[i] for i in range(len(val_pt)) if val_pt[i] >= th_pt]
        temp = np.mean(input_data[loc_i], axis=0)
        labelsq, distances = p.knn_query(temp, k=1)
        print(labelsq[0])
        tsi_list.append(labelsq[0][0])

    p1 = PARC(input_data, time_labels, jac_std_global=0.15, dist_std_local=1, knn=knn,
              too_big_factor=p1_too_big,
              path="/home/shobi/Trajectory/Datasets/" + "bcell/", pseudotime=True,
              super_cluster_labels=super_labels, super_node_degree_list=p0.node_degree_list,
              super_terminal_cells=tsi_list, root_user=1,
              x_lazy=0.99, alpha_teleport=0.99, preserve_disconnected=True, dataset='EB',
              super_terminal_clusters=p0.terminal_clusters, random_seed=p0_random_seed)

    p1.run_PARC()
    # adata.obs['parc1'] = [str(i) for i in p1.labels]
    # sc.pl.matrixplot(adata, marker_genes, groupby='parc1', dendrogram=True)
    labels = p1.labels
    '''
    df_labels  = pd.DataFrame({'p0_labels':p0.labels,'p1_labels':p1.labels})
    df_labels['sub_TS'] = [1 if i in p1.terminal_clusters else 0 for i in p1.labels]
    df_labels['super_TS'] = [1 if i in p0.terminal_clusters else 0 for i in p0.labels]
    df_labels.to_csv('/home/shobi/Trajectory/Datasets/EB_Phate/df_labels_knn20_pc100_seed20.csv')
    df_temp2 = pd.DataFrame(adata.X, columns=[i for i in adata.var_names])
    df_temp2 = df_temp2[marker_genes_list]
    df_temp2['parc1'] = [str(i) for i in labels]
    df_temp2 = df_temp2.groupby('parc1').mean()
    df_temp2.to_csv('/home/shobi/Trajectory/Datasets/EB_Phate/df_groupbyParc1_knn20_pc100_seed20.csv')
    '''

    adata.obs['parc1'] = [str(i) for i in labels]
    # df_ts = pd.DataFrame(adata.X, columns = [i for i in adata.var_names])
    # df_ts = df_ts[marker_genes_list]
    # df_ts['parc1'] =  [str(i) for i in labels]
    adata.obs['terminal_state'] = ['True' if i in p1.terminal_clusters else 'False' for i in labels]
    # df_ts = df_ts[df_ts['terminal_state']=='True']
    adata_TS = adata[adata.obs['terminal_state'] == 'True']
    # sns.clustermap(df_temp1, vmin=-1, vmax=1, xticklabels=True, yticklabels=True, row_cluster=False, col_cluster=True)
    sc.pl.matrixplot(adata, marker_genes_dict, groupby='parc1', vmax=1, vmin=-1, dendrogram=True)
    # sc.pl.matrixplot(adata_TS, marker_genes_dict, groupby='parc1', vmax=1, vmin=-1, dendrogram=True)

    # U = umap.UMAP(n_neighbors=10, random_state=0, repulsion_strength=repulsion_strength).fit_transform(input_data[:, 0:n_pcs])
    f, (ax1, ax2) = plt.subplots(1, 2, sharey=True)
    ax1.scatter(U[:, 0], U[:, 1], c=time_labels, s=5, cmap='viridis', alpha=0.5)
    ax2.scatter(U[:, 0], U[:, 1], c=p1.single_cell_pt_markov, s=5, cmap='viridis', alpha=0.5)
    plt.title('repulsion and knn and pcs ' + str(repulsion_strength) + ' ' + str(u_knn) + ' ' + str(
        n_pcs) + ' randseed' + str(p0_random_seed))
    plt.show()

    knn_hnsw, ci_list = sc_loc_ofsuperCluster_embeddedspace(U, p0, p1, np.arange(0, len(labels)))

    draw_trajectory_gams(U, ci_list, labels, super_labels, p0.edgelist_maxout,
                         p1.x_lazy, p1.alpha_teleport, p1.single_cell_pt_markov, time_labels, knn=p0.knn,
                         final_super_terminal=p1.revised_super_terminal_clusters,
                         sub_terminal_clusters=p1.terminal_clusters,
                         title_str='Markov Hitting Times (Gams)', ncomp=ncomps)

    draw_sc_evolution_trajectory_dijkstra(p1, U, knn_hnsw, p0.full_graph_shortpath,
                                          idx=np.arange(0, input_data.shape[0]), X_data=input_data)

    plt.show()


def main_mESC(ncomps=100, knn=30, p0_random_seed=12, run_palantir_func=False):
    import random
    rand_str = random.randint(1, 999)
    print('rand string', rand_str)
    knn = 20
    p0_random_seed = 20
    data_random_seed = 20
    root = '0.0'
    type_germ = 'Meso'
    normalize = True
    data = pd.read_csv('/home/shobi/Trajectory/Datasets/mESC/mESC_' + type_germ + '_15markers.csv')
    print('counts', data.groupby('day').count())
    # print(data.head())
    print(data.shape)
    n_sub = 7000
    print('type,', type_germ, 'nelements', n_sub, 'p0 randseed', p0_random_seed)
    title_string = 'randstr:' + str(rand_str) + ' Knn' + str(knn) + ' nelements:' + str(n_sub) + ' ' + 'meso'
    # data = data[data['day']!=0]

    p0_too_big = 0.3
    p1_too_big = 0.15
    print('p0 and p1 too big', p0_too_big, p1_too_big)
    data_sub = data[data['day'] == 0.0]
    np.random.seed(data_random_seed)
    idx_sub = np.random.choice(a=np.arange(0, data_sub.shape[0]), size=min(n_sub, data_sub.shape[0]), replace=False,
                               p=None)  # len(true_label)
    data_sub = data_sub.values[idx_sub, :]
    data_sub = pd.DataFrame(data_sub, columns=data.columns)
    for i in [1.0, 2, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0]:
        sub = data[data['day'] == i]
        print(sub.shape[0])
        np.random.seed(data_random_seed)
        idx_sub = np.random.choice(a=np.arange(0, sub.shape[0]), size=min(n_sub, sub.shape[0]), replace=False,
                                   p=None)  # len(true_label)
        sub = sub.values[idx_sub, :]
        sub = pd.DataFrame(sub, columns=data.columns)
        data_sub = pd.concat([data_sub, sub], axis=0, ignore_index=True, sort=True)
    # print(data_sub.groupby('day').count())
    # print(data.columns)
    true_label = data_sub['day']
    true_type = data_sub['type']
    data = data_sub.drop(['day', 'Unnamed: 0', 'type'], axis=1)
    # print('after subbing', data.head)
    cols = ['Sca-1', 'CD41', 'Nestin', 'Desmin',
            'CD24', 'FoxA2', 'Oct4', 'CD45', 'Ki67', 'Vimentin',
            'Nanog', 'pStat3-705', 'Sox2', 'Flk-1', 'Tuj1',
            'H3K9ac', 'Lin28', 'PDGFRa', 'EpCAM', 'CD44',
            'GATA4', 'Klf4', 'CCR9', 'p53', 'SSEA1', 'IdU', 'Cdx2']  # 'bCatenin'

    meso_good = ['CD24', 'FoxA2', 'Oct4', 'CD45', 'Ki67', 'Vimentin', 'Cdx2', 'CD54', 'pStat3-705', 'Sox2', 'Flk-1',
                 'Tuj1', 'SSEA1', 'H3K9ac', 'Lin28', 'PDGFRa', 'bCatenin', 'EpCAM', 'CD44', 'GATA4', 'Klf4', 'CCR9',
                 'p53']
    marker_genes_ecto = ['Oct4', 'Nestin', 'CD45', 'Vimentin', 'Cdx2', 'Flk-1', 'PDGFRa', 'CD44',
                         'GATA4', 'CCR9', 'CD54', 'CD24', 'CD41', 'Tuji']
    marker_genes_meso_paper_sub = ['Oct4', 'CD54', 'SSEA1', 'Lin28', 'Cdx2', 'CD45', 'Nanog', 'Sox2', 'Flk-1', 'Tuj1',
                                   'PDGFRa', 'EpCAM', 'CD44', 'CCR9', 'GATA4']

    marker_genes_meso_paper = ['Nestin', 'FoxA2', 'Oct4', 'CD45', 'Sox2', 'Flk-1', 'Tuj1', 'PDGFRa', 'EpCAM', 'CD44',
                               'GATA4', 'CCR9', 'Nanog', 'Cdx2', 'Vimentin']  # 'Nanog''Cdx2','Vimentin'
    marker_genes_endo = ['Sca-1''Nestin', 'CD45', 'Vimentin', 'Cdx2', 'Flk-1', 'PDGFRa', 'CD44',
                         'GATA4', 'CCR9', 'CD54', 'CD24', 'CD41', 'Oct4']
    marker_genes_meso = ['Sca-1', 'CD41', 'Nestin', 'Desmin', 'CD24', 'FoxA2', 'Oct4', 'CD45', 'Ki67', 'Vimentin',
                         'Cdx2', 'Nanog', 'pStat3-705', 'Sox2', 'Flk-1', 'Tuj1', 'H3K9ac', 'Lin28', 'PDGFRa', 'EpCAM',
                         'CD44', 'GATA4', 'Klf4', 'CCR9', 'p53', 'SSEA1', 'bCatenin', 'IdU']  # 'IdU',

    marker_dict = {'Ecto': marker_genes_ecto, 'Meso': marker_genes_meso, 'Endo': marker_genes_meso}
    marker_genes = marker_dict[
        type_germ]  # ['Nestin',   'CD45', 'Vimentin', 'Cdx2', 'Flk-1', 'PDGFRa', 'EpCAM', 'CD44',   'GATA4', 'CCR9', 'CD54', 'CD24', 'CD41','Oct4'] #['FoxA2', 'Oct4', 'Nanog', 'Sox2', 'Tuj1']
    data = data[marker_genes]

    print('marker genes ', marker_genes)

    pre_fac_scale = [4, 1, 1]
    pre_fac_scale_genes = ['H3K9ac', 'Lin28', 'Oct4']
    for pre_scale_i, pre_gene_i in zip(pre_fac_scale, pre_fac_scale_genes):
        data[pre_gene_i] = data[pre_gene_i] / pre_scale_i
        print('prescaled gene', pre_gene_i, 'by factor', pre_scale_i)

    # for column_i in data.columns:
    # threshold = data[column_i].mean() + 7*data[column_i].std() #causes excessive fragmentation
    # data[data[column_i]> threshold] = threshold
    # data = data.drop(['Unnamed: 0'], axis=1)
    scale_arcsinh = 5
    raw = data.values
    raw = raw.astype(np.float)
    raw_df = pd.DataFrame(raw, columns=data.columns)
    # hist = raw_df.hist(bins = 100)
    # print('raw', raw)
    raw = raw / scale_arcsinh
    raw = np.arcsinh(raw)
    # print(data.shape, raw.shape)

    adata = sc.AnnData(raw)
    adata.var_names = data.columns
    # print(adata.shape, len(data.columns))

    true_label_int = [i for i in true_label]
    adata.obs['day'] = ['0' + str(i) if i < 10 else str(i) for i in true_label_int]
    true_label_str = [str(i) for i in
                      true_label_int]  # the way find_root works is to match any part of root-user to majority truth

    print(adata.obs['day'])
    if normalize == True:
        sc.pp.scale(adata, max_value=5)
        print(colored('normalized', 'blue'))
    else:
        print(colored('NOT normalized', 'blue'))
    print('adata', adata.shape)
    # ncomps = 30

    # sc.tl.pca(adata, svd_solver='arpack', n_comps=ncomps)
    n_umap = adata.shape[0]

    np.random.seed(data_random_seed)
    idx = np.random.choice(a=np.arange(0, adata.shape[0]), size=adata.shape[0], replace=False,
                           p=None)  # len(true_label)

    udata = adata.X[idx, :][0:n_umap]

    # U = umap.UMAP().fit_transform(udata)
    # U_df = pd.DataFrame(U, columns=['x', 'y'])
    # U_df.to_csv('/home/shobi/Trajectory/Datasets/mESC/umap_89782cells_7000each_Randseed20_meso.csv')

    U = pd.read_csv('/home/shobi/Trajectory/Datasets/mESC/umap_89782cells_7000each_Randseed20_meso.csv')
    U = U.values[:, 1:]
    print(U.shape)

    true_label_int = list(np.asarray(true_label_int)[idx])
    # slingshot_annots = true_label_int[0:n_umap]
    # slingshot_annots = [int(i) for i in slingshot_annots]
    # Slingshot_annots = pd.DataFrame(slingshot_annots,columns = ['label'])
    # Slingshot_annots.to_csv('/home/shobi/Trajectory/Datasets/mESC/Slingshot_annots_int_10K.csv')
    true_label_str = list(np.asarray(true_label_str)[idx])
    true_type = list(np.asarray(true_type)[idx])
    adata = adata[idx]
    # Slingshot_data = pd.DataFrame(adata.X[0:n_umap], columns=marker_genes)
    # Slingshot_data.to_csv('/home/shobi/Trajectory/Datasets/mESC/Slingshot_input_data_10K.csv')
    # print('head sling shot data', Slingshot_data.head)
    # print('head sling shot annots', Slingshot_annots.head)

    # print('slingshot data shape', Slingshot_data.shape)
    # sling_adata =sc.AnnData(Slingshot_data)

    sc.tl.pca(adata, svd_solver='arpack', n_comps=20)
    # plt.scatter(sling_adata.obsm['X_pca'][:,0],sling_adata.obsm['X_pca'][:,1], c = Slingshot_annots['label'])
    plt.show()
    # sc.pl.matrixplot(adata, marker_genes_meso, groupby='day', dendrogram=True)
    t_pal_start = time.time()
    # run_palantir_mESC(adata[0:n_umap:], knn=knn, tsne=U, str_true_label = true_label_str[0:n_umap])
    print('palantir run time', round(time.time() - t_pal_start))

    p0 = PARC(adata.X, true_label_int, jac_std_global=0.15, dist_std_local=1, knn=knn,
              too_big_factor=p0_too_big,
              pseudotime=True, path="/home/shobi/Trajectory/Datasets/mESC/",
              root_user=root, dataset='mESC', random_seed=p0_random_seed,
              do_magic_bool=True, is_coarse=True, preserve_disconnected=False)  # *.4 root=1,
    p0.run_PARC()

    adata.obs['parc0'] = [str(i) for i in p0.labels]
    sc.pl.matrixplot(adata, marker_genes, groupby='parc0', dendrogram=True)

    p = hnswlib.Index(space='l2', dim=adata.X.shape[1])
    p.init_index(max_elements=adata.X.shape[0], ef_construction=100, M=16)
    p.add_items(adata.X)
    p.set_ef(30)
    tsi_list = []  # find the single-cell which is nearest to the average-location of a terminal cluster in PCA space (
    for tsi in p0.terminal_clusters:
        loc_i = np.where(np.asarray(p0.labels) == tsi)[0]
        val_pt = [p0.single_cell_pt_markov[i] for i in loc_i]
        th_pt = np.percentile(val_pt, 50)  # 50
        loc_i = [loc_i[i] for i in range(len(val_pt)) if val_pt[i] >= th_pt]
        temp = np.mean(adata.X[loc_i], axis=0)
        labelsq, distances = p.knn_query(temp, k=1)
        print(labelsq[0])
        tsi_list.append(labelsq[0][0])
    super_labels = p0.labels

    p1 = PARC(adata.X, true_label_int, jac_std_global=0.15, dist_std_local=1, knn=knn,
              too_big_factor=p1_too_big,
              path="/home/shobi/Trajectory/Datasets/" + "bcell/", pseudotime=True,
              super_cluster_labels=super_labels, super_node_degree_list=p0.node_degree_list,
              super_terminal_cells=tsi_list, root_user=root,
              x_lazy=0.99, alpha_teleport=0.99, preserve_disconnected=True, dataset='mESC',
              super_terminal_clusters=p0.terminal_clusters, random_seed=p0_random_seed)

    p1.run_PARC()
    adata.obs['parc1'] = [str(i) for i in p1.labels]
    sc.pl.matrixplot(adata, marker_genes, groupby='parc1', dendrogram=True)
    labels = p1.labels

    # X = adata.obsm['X_pca'][:,0:2]
    # print(X.shape)

    c_pt = p1.single_cell_pt_markov[0:n_umap]
    c_type = true_type[0:n_umap]
    dict_type = {'EB': 0, 'Endo': 5, "Meso": 10, 'Ecto': 15}
    c_type = [dict_type[i] for i in c_type]
    u_truelabel = true_label_int[0:n_umap]

    # U = umap.UMAP().fit_transform(adata.obsm['X_pca'][idx, 0:ncomps])

    print('umap done', rand_str, time.ctime())
    f, (ax1, ax2, ax3) = plt.subplots(1, 3, sharey=True)
    s_genes = ''
    for s in marker_genes:
        s_genes = s_genes + ' ' + s
    plt.title(str(len(true_label)) + 'cells ' + str(title_string) + '\n marker genes:' + s_genes, loc='left')
    ax1.scatter(U[:, 0], U[:, 1], c=u_truelabel, cmap='jet', s=4, alpha=0.7)
    ax2.scatter(U[:, 0], U[:, 1], c=c_pt, cmap='jet', s=4, alpha=0.7)
    ax3.scatter(U[:, 0], U[:, 1], c=c_type, cmap='jet', s=4, alpha=0.7)

    plt.show()

    knn_hnsw, ci_list = sc_loc_ofsuperCluster_embeddedspace(U, p0, p1, np.arange(0, len(labels)))
    true_label_formatted = [int(10 * i) for i in u_truelabel]
    draw_trajectory_gams(U, ci_list, labels, super_labels, p0.edgelist_maxout,
                         p1.x_lazy, p1.alpha_teleport, c_pt, true_label_formatted, knn=p0.knn,
                         final_super_terminal=p1.revised_super_terminal_clusters,
                         sub_terminal_clusters=p1.terminal_clusters,
                         title_str='Markov Hitting Times (Gams)', ncomp=ncomps)
    plt.show()


def run_palantir_mESC(ad, knn, tsne, str_true_label, start_cell='c4823'):
    t0 = time.time()
    norm_df_pal = pd.DataFrame(ad.X)
    # print('norm df', norm_df_pal)
    new = ['c' + str(i) for i in norm_df_pal.index]
    ncomps = ad.X.shape[1]
    loc_start = np.where(np.asarray(str_true_label) == '0.0')[0][0]
    start_cell = 'c' + str(loc_start)
    print('start cell', start_cell)
    norm_df_pal.index = new
    norm_df_pal.columns = [i for i in ad.var_names]
    # pca_projections, _ = palantir.utils.run_pca(norm_df_pal, n_components=ncomps)
    # print(type(pca_projections)) Dataframe
    pca_projections = norm_df_pal
    # sc.tl.pca(ad, svd_solver='arpack')
    dm_res = palantir.utils.run_diffusion_maps(pca_projections, knn=knn, n_components=ncomps)

    ms_data = palantir.utils.determine_multiscale_space(dm_res)  # n_eigs is determined using eigengap
    print('ms data', ms_data.shape)
    tsne = pd.DataFrame(tsne, columns=['x', 'y'])  # palantir.utils.run_tsne(ms_data)
    tsne.index = new
    # print(type(tsne))

    str_true_label = pd.Series(str_true_label, index=norm_df_pal.index)
    palantir.plot.plot_cell_clusters(tsne, str_true_label)

    # start_cell = 'c4823'  # '#C108 for M12 connected' #M8n1000d1000 start - c107 #c1001 for bifurc n2000d1000 #disconnected n1000 c108, "C1 for M10 connected" # c10 for bifurcating_m4_n2000d1000
    num_waypoints = 5000  # 1200 default
    pr_res = palantir.core.run_palantir(ms_data, early_cell=start_cell, num_waypoints=num_waypoints, knn=knn)
    print('time end palantir', round(time.time() - t0))
    palantir.plot.plot_palantir_results(pr_res, tsne, knn, ncomps)
    # plt.show()
    imp_df = palantir.utils.run_magic_imputation(norm_df_pal, dm_res)
    # imp_df.to_csv('/home/shobi/Trajectory/Datasets/HumanCD34/MAGIC_palantir_knn30ncomp100.csv')

    # genes = ['GATA1', 'GATA2', 'ITGA2B']#, 'SPI1']#['CD34','GATA1', 'IRF8','ITGA2B']
    # gene_trends = palantir.presults.compute_gene_trends( pr_res, imp_df.loc[:, genes])
    # palantir.plot.plot_gene_trends(gene_trends)
    # genes = ['MPO','ITGAX','IRF8','CSF1R','IL3RA']#'CD34','MPO', 'CD79B'
    # gene_trends = palantir.presults.compute_gene_trends(pr_res, imp_df.loc[:, genes])
    # palantir.plot.plot_gene_trends(gene_trends)
    plt.show()


def run_palantir_EB(ad, ncomps, knn, tsne, str_true_label):
    t0 = time.time()
    norm_df_pal = pd.DataFrame(ad.X)
    # print('norm df', norm_df_pal)
    new = ['c' + str(i) for i in norm_df_pal.index]

    loc_start = np.where(np.asarray(str_true_label) == '1')[0][0]
    start_cell = 'c' + str(loc_start)
    print('start cell', start_cell)
    norm_df_pal.index = new
    norm_df_pal.columns = [i for i in ad.var_names]
    pca_projections, _ = palantir.utils.run_pca(norm_df_pal, n_components=ncomps)

    # sc.tl.pca(ad, svd_solver='arpack')
    dm_res = palantir.utils.run_diffusion_maps(pca_projections, knn=knn, n_components=ncomps)

    ms_data = palantir.utils.determine_multiscale_space(dm_res)  # n_eigs is determined using eigengap
    print('ms data', ms_data.shape)
    tsne = pd.DataFrame(tsne, columns=['x', 'y'])  # palantir.utils.run_tsne(ms_data)
    tsne.index = new
    # print(type(tsne))

    str_true_label = pd.Series(str_true_label, index=norm_df_pal.index)
    palantir.plot.plot_cell_clusters(tsne, str_true_label)

    # start_cell = 'c4823'  # '#C108 for M12 connected' #M8n1000d1000 start - c107 #c1001 for bifurc n2000d1000 #disconnected n1000 c108, "C1 for M10 connected" # c10 for bifurcating_m4_n2000d1000
    num_waypoints = 1200  # 1200 default
    pr_res = palantir.core.run_palantir(ms_data, early_cell=start_cell, num_waypoints=num_waypoints, knn=knn)
    print('time end palantir', round(time.time() - t0))
    palantir.plot.plot_palantir_results(pr_res, tsne, knn, ncomps)
    # plt.show()
    # imp_df = palantir.utils.run_magic_imputation(norm_df_pal, dm_res)
    # imp_df.to_csv('/home/shobi/Trajectory/Datasets/HumanCD34/MAGIC_palantir_knn30ncomp100.csv')

    # genes = ['GATA1', 'GATA2', 'ITGA2B']#, 'SPI1']#['CD34','GATA1', 'IRF8','ITGA2B']
    # gene_trends = palantir.presults.compute_gene_trends( pr_res, imp_df.loc[:, genes])
    # palantir.plot.plot_gene_trends(gene_trends)
    # genes = ['MPO','ITGAX','IRF8','CSF1R','IL3RA']#'CD34','MPO', 'CD79B'
    # gene_trends = palantir.presults.compute_gene_trends(pr_res, imp_df.loc[:, genes])
    # palantir.plot.plot_gene_trends(gene_trends)
    plt.show()


def main():
    dataset = 'Toy'  # 'EB'#'mESC'#'Human'#,'Toy'#,'Bcell'  # 'Toy'
    if dataset == 'Human':
        main_Human(ncomps=10, knn=30, p0_random_seed=12, run_palantir_func=False)
    elif dataset == 'Bcell':
        main_Bcell(ncomps=100, knn=20, random_seed=4)  # 0 is good
    elif dataset == 'iPSC':
        main_iPSC(ncomps=100, knn=30, p0_random_seed=12, run_palantir_func=False)
    elif dataset == 'mESC':
        main_mESC(ncomps=100, knn=30, p0_random_seed=12, run_palantir_func=False)
    elif dataset == 'EB':
        main_EB(ncomps=140, knn=20, p0_random_seed=24)
        # plot_EB()
    else:
        main_Toy(ncomps=20, knn=20, random_seed=1)


if __name__ == '__main__':
    main()

