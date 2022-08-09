import copy
import itertools
import os
import sys
from collections import defaultdict
from sklearn.metrics.pairwise import euclidean_distances
from sklearn.metrics import confusion_matrix
import numpy as np
import pandas as pd
from sklearn import metrics

from sklearn.metrics.pairwise import cosine_distances
import lable_transform



### step4. format output
### infile: one line for one clique
### outfile: cluster ID in a column; line Number is the cell index


def output(clique_list, number_cells):
    if (clique_list is None) or (number_cells is None):
        sys.stderr.write("wrong argument number from output()")
        sys.exit(1)
    cell_clqID = {}

    clqID = 0
    for line in clique_list:
        cells = line.split(' ')
        cells = list(map(int, cells))  # index
        if len(cells) < 3:
            for c in cells:
                cell_clqID[c] = -1
        else:
            for c in cells:
                cell_clqID[c] = clqID
            clqID += 1

    index = []
    for c in range(1, number_cells + 1):
        if c in cell_clqID:
            index.append(cell_clqID[c] + 1)
        else:
            index.append(-1)

    return index


# end 4

### 3. delete overlap. After merging, if one cell appears in multiple cliques (and the cliques do not satisfy merging), select one cliq for the cell to be in. At the same time, delete the cell from the other cliques.
### criteria: select the cliq who has bigger average link weights to the node (by checking the SNN graph)
def uniq(clique_list, snn):
    # clique_list: clique output from merge()
    # edgeFile: pair of nodes and weigh of edge (3 column file)
    if clique_list is None:
        sys.stderr.write("wrong argument number from uniq()")
        sys.exit(1)

    # read in the edge file (node1\tnode2\tweight)
    edges = copy.deepcopy(snn)
    A = defaultdict(dict)
    for edge in edges:
        edge[0] = str(edge[0] + 1)
        edge[1] = str(edge[1] + 1)
    for lst in edges:
        A[lst[0]][lst[1]] = lst[2]
        A[lst[1]][lst[0]] = lst[2]

    # parse the clique list
    cell_cliq = defaultdict(list)
    cliq_cell = defaultdict(list)
    cliqNum = 1
    for line in clique_list:
        cells = line.split(' ')
        for c in cells:
            cell_cliq[c].append(str(cliqNum))
            cliq_cell[str(cliqNum)].append(c)
        cliqNum += 1

    # ------------------- unique assign----------------------------------------
    for c in cell_cliq.keys():  # for each node
        if len(cell_cliq[c]) > 1:  # if it is in more than one clique
            # count links in each clique associated with the cell
            count_link = defaultdict(list)  # key: cliq, value: weighted link in the cliq to the node
            for connect_node in A[c].keys():  # each neighbor of node c
                for cl in cell_cliq[connect_node]:  # for each clique that node c in
                    if cl in cell_cliq[c]:
                        count_link[cl].append(A[c][connect_node])
            # calculate the average of link weights connect from the cliq to the node c
            max_link = {}
            for cl in count_link.keys():
                max_link[cl] = sum(list(map(float, count_link[cl]))) / len(count_link[cl])
            # select the clique to assign the node c
            assign_cliq = max(max_link, key=max_link.get)
            # print c+" in "+" ".join(cell_cliq[c])+" assign: "+assign_cliq

            # assign to one and delete in other cliqs
            for cl in cell_cliq[c]:
                if not cl == assign_cliq:
                    cliq_cell[cl].remove(c)

    # --------------- output------------------------------------------
    uniqCliq_list = []
    for cl in sorted(list(map(int, cliq_cell.keys()))):
        if len(cliq_cell[str(cl)]) > 0:
            uniqCliq_list.append(" ".join(cliq_cell[str(cl)]) + '\n')
    return uniqCliq_list


## end 3.

### step2. merge quasi-clique. Some cluster are long and extended. Need to merge quasi-cliques to find such cluster.
### be aware that after merging, the new clusters generated are bigger and have the potential to be merged again.
### cutoff: the shared must exceed the cutoff percent in one clique to be merged
def merge(clique_list, merge_cutoff):
    # clique_list: clique output from findquasicliq(). one line is space deliminated indices of a cluster.
    # cutoff: threshold of overlapping rate for merging
    if (clique_list is None):
        sys.stderr.write("wrong argument number from merge()")
        sys.exit(1)
    # if cutoff is None:    cutoff = 0.5  #
    cell_cliq = defaultdict(list)  # key: cell ID, value: a list of cliq ID(str) that the cell belongs to
    cliq_cell = defaultdict(list)  # key: cliq ID(str), value: a list of cells ID in the cliq
    cliqNum = 1

    for line in clique_list:
        cells = line.split(' ')
        for c in cells:
            cell_cliq[c].append(str(cliqNum))
            cliq_cell[str(cliqNum)].append(c)
        cliqNum += 1

    # ------------- inner merge cycle----------------------------
    merged_bl = mergeOnline(merge_cutoff, cell_cliq, cliq_cell)
    while merged_bl:
        merged_bl = mergeOnline(merge_cutoff, cell_cliq, cliq_cell)

    # ------------- output --------------------------------------
    mergedCliq_list = []
    for cl in cliq_cell.keys():
        mergedCliq_list.append(" ".join(cliq_cell[cl]))
    return mergedCliq_list


# 2a. on-line merging algorithm. refresh the cliques and re-do the candidate searching after each merge happens.
# sort the candidate of merging by the size of cliques, this will allow bigger clique join small cliques first, instead of small cliques join first.
def mergeOnline(cutoff, cell_cliq, cliq_cell):
    # the function will make one possible merge and return

    overlapCliq = {}  # pairs of cliques that have overlap in between
    # overlapCliq: key is pair of clique names, value is Number of cells overlapping between them
    for c in cell_cliq.keys():
        if len(cell_cliq[c]) > 1:
            if len(cell_cliq[c]) > 2:  ## pair-wise if 1 cell appear in more than 2 cliques.
                s = list(itertools.combinations(cell_cliq[c], 2))
                for pair in s:
                    grp = " ".join(pair)
                    if grp in overlapCliq:
                        overlapCliq[grp] += 1
                    else:
                        overlapCliq[grp] = 1
            else:
                grp = " ".join(cell_cliq[c])
                if grp in overlapCliq:
                    overlapCliq[grp] += 1
                else:
                    overlapCliq[grp] = 1

    # select overlapped cliques to merge
    # Since one cliq can overlap with multiple cliqs, create a score to sort all possible mergings
    # score is the size of the cliques to merge
    cliq2Merge = {}
    for grp in overlapCliq.keys():
        clqs = grp.split(' ')
        ol = overlapCliq[grp]
        bl = 0  # boolean to see if it qualify a merge
        ss = 0  # sum of score (sum of overlap proportion in each cliq of the group)
        sum_size = 0
        for cl in clqs:
            sum_size += len(cliq_cell[cl])
            # algo2: overlapping rate only need to exceed cutoff in one cliq
            score = float(ol) / len(cliq_cell[cl])
            ss += score
            if score >= cutoff:
                bl = 1
        if bl == 1:
            cliq2Merge[grp] = sum_size

    # online merge: merge only one candidate group, then refresh.
    # merge the one with the biggest score
    currCliqNum = max(list(map(int, cliq_cell.keys()))) + 1
    if len(cliq2Merge.keys()):
        grp = max(cliq2Merge, key=cliq2Merge.get)
        # print "merge "+grp+": "+str(cliq2Merge[grp])
        new = {}
        for cl in grp.split(' '):
            for c in cliq_cell[cl]:
                new[int(c)] = ''
                # refresh the cell_cliq for on-line learning
                index = cell_cliq[c].index(cl)
                del cell_cliq[c][index]  # delete old cliq index
                if str(currCliqNum) not in cell_cliq[c]:  # add new cliq index
                    cell_cliq[c].append(str(currCliqNum))
            del cliq_cell[cl]
        cliq_cell[str(currCliqNum)] = list(map(str, sorted(new.keys())))

    return len(cliq2Merge.keys())


# end of mergeInner
## end 2. merge()

### step 1. find quasi-clique
# find a r-quasi-clique associated with each node greedily
# inFile: pair-wise similarity #format: "node_index node_index edge_similarity\n"
# r: cutoff for quasi-clique
def findQuasiCliq(snn, r):
    # if r is None:    r = 0.7  #
    minCliqueSize = 3  # minimum acceptable clique size

    nodehash = defaultdict(list)
    edges = copy.deepcopy(snn)
    for edge in edges:
        edge[0] = str(edge[0] + 1)
        edge[1] = str(edge[1] + 1)
    for lst in edges:
        if len(lst) < 3 or (not lst[0].isdigit()) or (not lst[1].isdigit()):
            sys.stderr.write(
                "Error: input file not in the right format:\nIndex_of_node1 Index_of_node2 Weight_of_edge\n")
            sys.exit(1)
        try:
            float(lst[2])
        except ValueError:
            sys.stderr.write(
                "Error: input file not in the right format:\nIndex_of_node1 Index_of_node2 Weight_of_edge\n")
            sys.exit(1)
        if float(lst[2]) > 0:
            nodehash[lst[0]].append(lst[1])
            nodehash[lst[1]].append(lst[0])

    # -----------------find clique for each node -------------------
    cliques = {}
    for node in sorted(nodehash):
        neighList = list(nodehash[node])  ### get all neighbors
        while 1:
            if len(neighList) < (minCliqueSize - 1):
                break
            degreeHash = {}  ### each neighbor connect to how many of the other neighbors
            for neighNode in neighList:
                neighNeighList = list(nodehash[neighNode])
                degree = len(set(neighNeighList) & set(neighList)) + 1
                degreeHash[neighNode] = degree

            ### greedy: start from the neighbor with the least connection to other neighbors
            minDegNeigh = min(degreeHash, key=degreeHash.get)
            ## %NeighHash length is the number of all neighbors to the Node (including the minDegNeigh itself
            if degreeHash[minDegNeigh] >= int(len(neighList) * r + 1):
                ###  the local cluster satisfy to be a quasi-clique
                break
            else:
                ### satisfy, delete the neighbor
                neighList.remove(minDegNeigh)

        # quasi-cliq found
        if len(neighList) >= (minCliqueSize - 1):
            neighList.append(node)
            neighList.sort(key=int)
            cliques[" ".join(neighList)] = len(neighList)

    # ------------------ delete redundant clique -----------------------
    ### delete cliques that are part of other cliques
    cliques_clean = {}
    for currCliq in sorted(cliques, key=cliques.get, reverse=True):
        bl = 1  # bl=1: unique ; bl=0: redundant
        for existCliq in sorted(cliques_clean, key=cliques_clean.get, reverse=True):
            if (cliques_clean[existCliq] <= cliques[currCliq]):
                break
            else:
                bl = 0
                currCliqAry = currCliq.split(" ")
                existCliqAry = existCliq.split(" ")
                for win in currCliqAry:
                    if win not in existCliqAry:
                        bl = 1  # unique
                        break
                if bl == 0:
                    break
        if bl:
            cliques_clean[currCliq] = cliques[currCliq]

    max_ID = max(list(map(int, nodehash.keys())))
    return (cliques_clean.keys(), max_ID)


# end 1.
################       end of algorithm         #########
def SNN(dmat, k):
    """
    Contruct shared nearest neighbors graph based on primary distance matrix

    Input
    -----------
    *dmat:      primary distant matrix of data, eg. pairewise euclidean
                distance matrix.
    *k:         K nearest neighbors for finding shared neighbors

    Return
    -----------
    *SNN affinity graph
    """

    numSpl, n = dmat.shape
    if numSpl != n:
        raise ValueError('dmat must be square form matrix')
    elif dmat.min() < 0:
        raise ValueError('distance values shuold be positive.')

    IDX = np.argsort(dmat, axis=1)[:, :k] + 1  # KNN list
    # snn = np.zeros_like(dmat,dtype=np.float32)
    edges = []  # SNN graph
    for i in range(numSpl):
        j = i
        while j < numSpl - 1:
            j = j + 1
            shared = np.intersect1d(IDX[i, :], IDX[j, :])
            if len(shared) > 0:
                match1 = np.array([np.where(IDX[i, :] == idx)[0][0] for idx in shared]) + 1
                match2 = np.array([np.where(IDX[j, :] == idx)[0][0] for idx in shared]) + 1
                s = k - 0.5 * (match1 + match2)
                strength = max(s)  # weight
                if strength > 0:
                    # snn[i,j] = strength
                    # snn[j,i] = strength
                    edges.append([i, j, strength])
    return edges


# def snn_cliq(dmat, merge_cutoff=0.5, r_cutoff=0.7, number_cells=None):
def snn_cliq(dmat, merge_cutoff, r_cutoff, K=None, number_cells=None):
    """SNN-Cliq clustering"""
    cl = []
    if (r_cutoff > 1) or (r_cutoff <= 0) or (merge_cutoff > 1) or (merge_cutoff <= 0):
        raise ("Error: parameters are not in the right range.\n")
    if K is None:
        K = 3
    print("K",K)
    snn = SNN(dmat, K)

    cliques  = []
    results = findQuasiCliq(snn, r_cutoff)
    cliques = results[0]
    max_ID = results[1]
    if number_cells is None:
        number_cells = max_ID
    merge_cliques = []
    merge_cliques = merge(cliques, merge_cutoff)
    number_of_clusters = len(merge_cliques)
    cl.append(len(merge_cliques))
    uniq_cliques = []
    uniq_cliques = uniq(merge_cliques, snn)
    return output(uniq_cliques, number_cells)


def load_W(path, name):
    os.chdir(path)
    data = pd.read_csv(name, sep='\t')
    return (data)





