from itertools import imap
import collections, operator
from . import kmeans

class ClusterAndReducer:
    '''
    A functor that clusters a bundle of reads,
    indentifies the parent UMIs and returns the selected reads, umis and counts
    Methods:
      ** get_adj_list ** - returns the edges connecting the UMIs
      ** connected_components ** - returns clusters of connected components
        susing the edges in the adjacency list
      ** post_process_components** - make sure the connected components
        are suitable for downstream analysis
      ** get_best ** - returns the parent UMI(s) in the connected_components
      ** reduce_clusters ** - loops through the connected components in a
        cluster and returns the unique reads.
    '''

    ############
    # Utility functions #
    ############

    def breadth_first_search(self, node, adj_list):
        searched = set()
        found = set()
        queue = set()
        queue.update((node,))
        found.update((node,))

        while len(queue) > 0:
            node = (list(queue))[0]
            found.update(adj_list[node])
            queue.update(adj_list[node])
            searched.update((node,))
            queue.difference_update(searched)

        return found

    ##################
    # Compute graph methods #
    ##################

    def _get_adj_list_directional_(self, umis, counts, threshold):
        ''' identify all umis within the hamming distance threshold
        and where the counts of the first umi is > (2 * second umi counts)-1'''

        return {umi: [umi2 for umi2 in umis if
                      kmeans.hamming(umi.encode('utf-8'),
                                    umi2.encode('utf-8')) == threshold and
                      counts[umi] >= (counts[umi2] * 2) - 1] for umi in umis}

    def _get_adj_list_kmeans_(self, umis, counts, threshold):
        ''' identify all umis within the hamming distance threshold
        and where the counts of the first umi is > (2 * second umi counts)-1'''

        return {umi: [umi2 for umi2 in umis if
                      kmeans.hamming(umi.encode('utf-8'),
                                    umi2.encode('utf-8')) == threshold] for umi in umis}

    #########################
    # Post-process components methods   #
    #########################

    def _post_process_components_directional_(self, umis, components, adj_list, counts):
        # Make sure UMIs are assigned to only one cluster
        for umi in umis:
            parent_clusters = filter(lambda x: (x & set([umi])) != set(), components)
            if len(parent_clusters) > 1:
                # Reassign to cluster whose representative has highest count
                cluster_reps = [self.get_best(cluster, counts) for cluster in parent_clusters]
                index_rep = cluster_reps.index(max(cluster_reps))
                for i in range(len(cluster_reps)):
                    if i != index_rep:
                        components[components.index(parent_clusters[i])].remove(umi)

        return components

    def _post_process_components_kmeans_(self, umis, components, adj_list, counts):
        # RUN k-means algorithm
        # to identify possible subclusters
        new_components = []
        for cluster in components:
            if len(cluster) == 1:
                new_components.append(cluster)
            else:
                # restrict both counts and adj_list to the UMIs that appear in cluster
                counts_restricted = {umi: counts[umi] for umi in cluster}
                adj_list_restricted = {umi: adj_list[umi] for umi in cluster}

                new_clusters = kmeans.find_clusters(adj_list_restricted,
                                                    counts_restricted, k=1)

                for new_cluster in new_clusters:
                    new_components.append(cluster)

        return new_components

    ##########################
    # Methods common to both approaches #
    ##########################

    def get_connected_components(self, umis, graph, counts):
        ''' find the connected UMIs within an adjacency dictionary'''

        found = set()
        components = list()

        for node in sorted(graph, key=lambda x: counts[x], reverse=True):
            if node not in found:
                component = self.breadth_first_search(node, graph)
                found.update(component)
                components.append(component)

        return components

    def get_best(self, cluster, counts):
        ''' return the UMI with the highest counts'''
        if len(cluster) == 1:
            return list(cluster)[0]
        else:
            sorted_nodes = sorted(cluster, key=lambda x: counts[x],
                                  reverse=True)
            return sorted_nodes[0]

    def reduce_clusters(self, bundle, clusters, counts):
        ''' collapse clusters down to the UMI which accounts for the cluster
        using the adjacency dictionary and return the list of final UMIs'''
        reads = []

        for cluster in clusters:
            # If there is only one UMI in a cluster, no need to correct anything
            if len(cluster) > 1:
                parent_umi = self.get_best(cluster, counts)
                reads += [(read, parent_umi) for umi in cluster if umi != parent_umi for read in bundle[umi]]

        return reads

    # Initialization step
    def __init__(self, cluster_method="kmeans"):
        ''' select the required class methods for the cluster_method'''

        if cluster_method == "directional":
            self.get_adj_list = self._get_adj_list_directional_
            self.post_process_components = self._post_process_components_directional_

        elif cluster_method == "kmeans":
            self.get_adj_list = self._get_adj_list_kmeans_
            self.post_process_components = self._post_process_components_kmeans_

    # Call method
    def __call__(self, bundle, threshold = 1):

        umis = bundle.keys()

        len_umis = [len(x) for x in umis]
        assert max(len_umis) == min(len_umis), (
            "not all umis are the same length(!):  %d - %d" % (
                min(len_umis), max(len_umis)))

        counts = {umi: len(bundle[umi]) for umi in umis}

        adj_list = self.get_adj_list(umis, counts, threshold)
        clusters = self.get_connected_components(umis, adj_list, counts)
        clusters = self.post_process_components(umis, clusters, adj_list, counts)
        reads_to_modify = self.reduce_clusters(bundle, clusters, counts)

        return reads_to_modify
