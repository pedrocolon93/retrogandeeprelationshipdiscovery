from threading import Thread, Lock

from CNQuery import CNQuery
from tools import *
# import conceptnet5


if __name__ == '__main__':
    # test connection
    print(CNQuery().query_and_parse('/c/en/man', '/c/en/woman'))
    # find n synonyms using basic word embedding
    nearest_concepts_amount = 50
    cross_concepts_amount = 400
    concept_1 = "phone"
    # concept_1 = "man"
    # concept_1 = "smartphone"
    # concept_1 = "uber"
    # concept_1 = "application"
    # relationship_type = "/r/Desires"
    # relationship_type = "/r/FormOf"
    # relationship_type = "/r/NotCapableOf"
    relationship_type = "/r/UsedFor"
    # relationship_type = "/r/CapableOf"
    # concept_2 = "pizza"
    # concept_2 ="rideshare"
    # concept_2 = "food"
    concept_2 = "picture"

    print(concept_1,relationship_type,concept_2)
    concept_vectors = find_in_retrofitted([concept_1, concept_2], return_words=True,dataset="numberbatch")
    # Nearest to concepts
    # concept1_neighbors_words,concept1_neighbors_vectors = find_closest(concept_vectors[0],n_top=nearest_concepts_amount, skip=0)
    # concept2_neighbors_words,concept2_neighbors_vectors = find_closest(concept_vectors[1],n_top=nearest_concepts_amount, skip=0)
    # Nearest across concepts
    class ThreadWithReturnValue(Thread):
        def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, *, daemon=None):
            Thread.__init__(self, group, target, name, args, kwargs, daemon=daemon)

            self._return = None

        def run(self):
            if self._target is not None:
                self._return = self._target(*self._args, **self._kwargs)

        def join(self):
            Thread.join(self)
            return self._return



    print("Loading concept 1 cross closest neighbors")
    # c1w, c1v,c1ww = find_closest_2(concept_vectors[0],n_top=nearest_concepts_amount)
    # concept1_neighbors_words,concept1_neighbors_vectors = find_cross_closest_2(concept_vectors[0],concept_vectors[1],n_top=cross_concepts_amount,closest=0,verbose=True)
    twrv1 = ThreadWithReturnValue(target=find_cross_closest_2, args=(concept_vectors[0],concept_vectors[1]),kwargs={"n_top":cross_concepts_amount,"closest":0,"verbose":True})

    print("Done.\nLoading concept 2 cross closest neighbors.")
    # concept2_neighbors_words,concept2_neighbors_vectors = find_cross_closest_2(concept_vectors[0],concept_vectors[1],n_top=cross_concepts_amount,closest=1,verbose=True)
    twrv2 = ThreadWithReturnValue(target=find_cross_closest_2, args=(concept_vectors[0],concept_vectors[1]),kwargs={"n_top":cross_concepts_amount,"closest":1,"verbose":True})
    twrv1.start()
    twrv2.start()
    concept1_neighbors_words, concept1_neighbors_vectors = twrv1.join()
    concept2_neighbors_words, concept2_neighbors_vectors = twrv2.join()
    if "/c/en/camera" in concept1_neighbors_words:
        print("in c1 neighs")
    if "/c/en/camera" in concept2_neighbors_words:
        print("in c2 neighs")
    print("Done")
    filtered = [x for x in concept2_neighbors_words if x not in concept1_neighbors_words]
    c2w = c2v = []
    for word in filtered:
        c2w.append(word)
    cutoff_amount = 1
    # Nearest together concepts
    ##TODO FIND THE NEAREST CONCEPTS TO THE ADDITION/SUBTRACTION OF THE 2 CONCEPTS
    current_iter = 0
    thread_list = []
    threadlimit = 32
    count=0
    print("Parameters cutoff:%i nearest concepts amount:%i" %(cutoff_amount,nearest_concepts_amount))

    print(str(len(concept1_neighbors_words)*len(c2w)))
    lock = Lock()
    i = 0
    words_to_explore = concept1_neighbors_words + concept2_neighbors_words
    remove_dups = True
    if remove_dups:
        words_to_explore = list(set(words_to_explore))
    print("Exploring",len(words_to_explore),len(words_to_explore)**2)
    connection_amount = 0
    connection_weight = 0
    cutoff_threshold_reached = False
    for c1_idx, concept1_neighbor in enumerate(words_to_explore):

        for c2_idx, concept2_neighbor in enumerate(words_to_explore):
            # i+=1
            if len(thread_list)> threadlimit or c2_idx+1==len(words_to_explore):
                for thread in thread_list:
                    thread.start()
                for thread in thread_list:
                    amt,wght = thread.join()
                    connection_amount+=amt
                    connection_weight+=wght
                thread_list.clear()
            def query_function(concept2_neighbor):
                amount, weight = CNQuery().query_and_parse(concept1_neighbor, concept2_neighbor, relationship_type)
                return amount, weight
            thread_list.append(ThreadWithReturnValue(group=None,target=query_function,args=(concept2_neighbor,)))
            # query_function(concept2_neighbor)
            # if len(thread_list)<threadlimit:
            #     thread_list.append(thread)
            # else:
            #     while True:
            #         for i, t in enumerate(thread_list):
            #             if not t.is_alive():
            #                 thread_list[i]=thread
            #                 break
            #             else:
            #                 t.join()
            # thread.start()


    # for c1_idx, concept1_neighbor in enumerate(concept1_neighbors_words):
    #     lock = Lock()
    #     for c2_idx, concept2_neighbor in enumerate(c2w):
    #         lock.acquire()
    #         if cutoff_threshold_reached:
    #             lock.release()
    #             for t in thread_list:
    #                 t.join()
    #             break
    #         else:
    #             lock.release()
    #         # check neighbor 1 with neighbor 2
    #         thread = Thread(group=None, target=query_function, args=(c2_idx, concept2_neighbor, lock))
    #         if len(thread_list)<threadlimit:
    #             thread_list.append(thread)
    #         else:
    #             found_empty = False
    #             target_thread_index = -1
    #             while not found_empty:
    #                 for t_idx, eval_thread in enumerate(thread_list):
    #                     if not eval_thread.is_alive():
    #                         target_thread_index = t_idx
    #                         found_empty = True
    #                         break
    #             thread_list[target_thread_index] = thread
    #         thread.start()
    #     for t in thread_list:
    #         t.join()
    #     print(count)

    print("The strength of that assumption is:")
    print(connection_amount)
    print(connection_weight)
    # find nodes in graph
    # see if connection exists
    # average it
