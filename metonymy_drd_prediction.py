from threading import Thread, Lock

import deep_relationship_discovery
import tools
from CNQuery import CNQuery
from deep_relationship_discovery import load_model_ours
from tools import *

# import conceptnet5


if __name__ == '__main__':
    # test connection
    # print(CNQuery().query_and_parse('/c/en/man', '/c/en/woman'))
    # find n synonyms using basic word embedding
    nearest_concepts_amount = 5
    cross_concepts_amount = 20
    dimensionality = 300
    tools.dimensionality = dimensionality
    drd_models_path = "trained_models/deepreldis/2019-05-28"
    target_file_loc = 'trained_models/retroembeddings/2019-05-15 11:47:52.802481/retroembeddings.h5'
    target_voc = pd.read_hdf(target_file_loc, 'mat')

    triple_list = [("orange","/r/AtLocation","supermarket"),
                   ("snowman","/r/CapableOf","running"),
                   ("man", "/r/CapableOf", "running"),
                   ("cat","/r/Desires","pizza"),
                   ("building","/r/UsedFor","photography"),
                   ("atom","/r/SimilarTo","solar system")]

    for triple in triple_list:
        print("*"*10)
        concept_1, relationship_type, concept_2 = triple
        print(concept_1, relationship_type, concept_2)
        concept_vectors = find_in_dataset([concept_1, concept_2], dataset=target_voc)


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
        twrv1 = ThreadWithReturnValue(target=find_cross_closest_dataset, args=(concept_vectors[0], concept_vectors[1]),
                                      kwargs={"n_top": cross_concepts_amount, "closest": 0, "verbose": True,
                                              "dataset": target_voc})
        # twrv1 = ThreadWithReturnValue(target=find_closest_in_dataset, args=(concept_vectors[0], target_voc),
        #                               kwargs={"n_top": cross_concepts_amount, "verbose": True
        #                                       })

        print("Done.\nLoading concept 2 cross closest neighbors.")
        # concept2_neighbors_words,concept2_neighbors_vectors = find_cross_closest_2(concept_vectors[0],concept_vectors[1],n_top=cross_concepts_amount,closest=1,verbose=True)
        twrv2 = ThreadWithReturnValue(target=find_cross_closest_dataset, args=(concept_vectors[0], concept_vectors[1]),
                                      kwargs={"n_top": cross_concepts_amount, "closest": 1, "verbose": True,
                                              "dataset": target_voc})
        # twrv2 = ThreadWithReturnValue(target=find_closest_in_dataset, args=(concept_vectors[1], target_voc),
        #                               kwargs={"n_top": cross_concepts_amount, "verbose": True
        #                                       })


        twrv1.start()
        twrv2.start()
        concept1_neighbors_words, concept1_neighbors_vectors = twrv1.join()
        concept2_neighbors_words, concept2_neighbors_vectors = twrv2.join()

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
        count = 0
        print("Parameters cutoff:%i nearest concepts amount:%i" % (cutoff_amount, nearest_concepts_amount))

        print(str(len(concept1_neighbors_words) * len(c2w)))
        lock = Lock()
        i = 0
        words_to_explore = concept1_neighbors_words + c2w
        remove_dups = True
        if remove_dups:
            words_to_explore = list(set(words_to_explore))
        print("Exploring", len(words_to_explore), len(words_to_explore) ** 2)
        cutoff_threshold_reached = False
        rel_values = []
        norm_rel_values = []
        rel=relationship_type.replace("/r/","")

        drd_model = load_model_ours(save_folder=drd_models_path, model_name=rel)
        normalizers = deep_relationship_discovery.normalize_outputs(None, save_folder=drd_models_path,use_cache=True)
        print("Exploring:", words_to_explore)
        rw1 = []
        rw2 = []
        for c1_idx, concept1_neighbor in enumerate(words_to_explore):
            for c2_idx, concept2_neighbor in enumerate(words_to_explore):
                if concept2_neighbor == concept1_neighbor:
                    continue
                start_vec, end_vec = find_in_dataset([concept1_neighbor, concept2_neighbor], target_voc)
                rw1.append(start_vec.reshape(1, tools.dimensionality))
                rw2.append(end_vec.reshape(1, tools.dimensionality))
        print("Predicting")
        np_rw1 = np.array(rw1)
        np_rw2 = np.array(rw2)
        inferred_res = drd_model[rel].predict(x={"retro_word_1": np_rw1.reshape(np_rw1.shape[0],np_rw1.shape[-1]),
                                                 "retro_word_2": np_rw2.reshape(np_rw2.shape[0],np_rw2.shape[-1])})
        print("Normalizing")
        norm_res = normalizers[rel].transform(inferred_res)
        print("Huzzah")
        print("The strength of that assumption is:")
        print(np.mean(inferred_res))
        print("The normalized strength")
        print(np.mean(norm_res))
        print(np.median(norm_res))
        print()
