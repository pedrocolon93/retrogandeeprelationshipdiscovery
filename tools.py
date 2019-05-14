import math
import multiprocessing
import operator
import os
import pickle
from multiprocessing.pool import Pool

import fastText
import gc
import numpy as np
import pandas as pd
from conceptnet5.nodes import standardized_concept_uri
from keras import backend as K
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler
from tensorflow.contrib.learn.python.learn.estimators._sklearn import train_test_split

directory = './retrogan/'
# directory = '/home/pedro/Documents/mltests/retrogan/'
# directory = '/home/conceptnet/conceptnet5/data/vectors/'
# original = 'fasttext-opensubtitles.h5'
original = 'crawl-300d-2M.h5'
# retrofitted = 'fasttext-opensubtitles-retrofit.h5'
retrofitted = 'crawl-300d-2M-retrofit.h5'


def process_line(line):
    linesplit = line.split(" ")
    if len(linesplit)<3:
        return None
    x = np.array([float(x) for x in linesplit[1:]])
    if(np.isnan(x).any()):
        print("Nan!?!??!")
        return None
    tup = (linesplit[0],x)
    return tup

def root_mean_squared_error(y_true, y_pred):
    return K.sqrt(K.mean(K.square(y_pred - y_true)))

def load_embedding(path,limit=100000000,cache=None):
    if cache is not None:
        words,vectors = pickle.load(cache)
        return words,vectors
    if os.path.exists(path):
        words = []
        vectors = []
        # f = open(path,encoding="utf-8")
        skip_first = True
        print("Starting loading",path)
        pool = Pool(multiprocessing.cpu_count())
        with open(path,encoding="utf-8") as source_file:
            # chunk the work into batches of 4 lines at a time
            results = pool.map(process_line, source_file, multiprocessing.cpu_count())
            for line in results:
                if line is None:
                    continue
                else:
                    words.append(line[0])
                    vectors.append(line[1])
        pool.close()
        pool.join()
        print("Finished")
        if cache is not None:
            pickle.dump((words,vectors),cache)
        return words,vectors
    else:
        raise FileNotFoundError(path+" does not exist")


common_vectors_train = None
common_retro_vectors_train = None
common_vectors_test = None
common_retro_vectors_test = None


def load_training_input(limit=10000):
    global common_retro_vectors_train, common_retro_vectors_test, common_vectors_test, common_vectors_train
    words, vectors = load_embedding("retrogan/wiki-news-300d-1M-subword.vec", limit=limit)
    retrowords, retrovectors = load_embedding("retrogan/numberbatch", limit=limit)
    print(len(words), len(retrowords))
    common_vocabulary = set(words).intersection(set(retrowords))
    common_vocabulary = np.array(list(common_vocabulary))
    common_retro_vectors = np.array([retrovectors[retrowords.index(word)] for word in common_vocabulary])
    common_vectors = np.array([vectors[words.index(word)] for word in common_vocabulary])
    X_train, X_test, y_train, y_test = train_test_split(common_vectors, common_retro_vectors, test_size=0.33,
                                                        random_state=42)
    common_vectors_train = X_train
    common_retro_vectors_train = y_train
    common_vectors_test = X_test
    common_retro_vectors_test = y_test
    del retrowords, retrovectors, words, vectors
    print("Size of common vocabulary:" + str(len(common_vocabulary)))
    return common_vocabulary, common_vectors, common_retro_vectors

datasets = {
    'fasttext':['fasttext-opensubtitles.h5','fasttext-opensubtitles-retrofit.h5'],
    'crawl':['crawl-300d-2M.h5','crawl-300d-2M-retrofit.h5'],
    'w2v':['w2v-google-news.h5','w2v-google-news-retrofit.h5'],
    'numberbatch':['mini.h5','mini.h5'],
    'retrogan':["retroembeddings.h5","retroembeddings.h5"]
}
def load_training_input_3(seed=42,test_split=0.1,dataset="fasttext"):

    global original,retrofitted
    original,retrofitted = datasets[dataset]
    print("Searching in")
    print(directory)
    print("for:", original, retrofitted)

    o = pd.read_hdf(directory + original, 'mat', encoding='utf-8')

    # print(asarray1.shape)
    # print(o["index"][0])
    # print(o["columns"][0][:])
    r = pd.read_hdf(directory + retrofitted, 'mat', encoding='utf-8')
    r_sub = r.loc[o.index.intersection(r.index), :]
    del r
    gc.collect()
    # print(asarray2.shape)
    X_train, X_test, y_train, y_test = train_test_split(o.values, r_sub.values, test_size = test_split, random_state = seed)
    common_vectors_train = X_train
    common_retro_vectors_train = y_train
    common_vectors_test = X_test
    common_retro_vectors_test = y_test
    # del retrowords, retrovectors, words, vectors
    del o
    gc.collect()
    # print("Size of common vocabulary:" + str(len(common_vocabulary)))
    return common_vectors_train, common_retro_vectors_train, common_vectors_test, common_retro_vectors_test

def mult(tup):
    return tup[0]*tup[1]
thread_amount = 8
pool = Pool(thread_amount)

def dot_product2_mp(v1, v2):
    it = [x for x in zip(list(v1.reshape(dimensionality)), list(v2.reshape(dimensionality)))]

    res = pool.map(mult,it)
    # pool.join()
    res = sum(res)
    # print(res)
    return res

def dot_product2(v1,v2):
    return sum(map(operator.mul,v1.reshape(dimensionality),v2.reshape(dimensionality)))

def vector_cos5(v1, v2):
    prod = dot_product2(v1, v2)
    len1 = math.sqrt(dot_product2(v1, v1))
    len2 = math.sqrt(dot_product2(v2, v2))
    return prod / (len1 * len2)

def load_noisiest_words(seed=42, test_split=0.1, dataset="fasttext"):
    global original, retrofitted
    if os.path.exists("filtered_x") and os.path.exists("filtered_y") and \
            os.path.exists("filtered_x_test") and os.path.exists("filtered_x_test"):
        print("Reusing cache")
        X_train = pd.read_hdf("filtered_x", 'mat', encoding='utf-8')
        Y_train = pd.read_hdf("filtered_y",'mat',encoding='utf-8')
        X_test = pd.read_hdf("filtered_x_test", "mat",encoding='utf-8')
        Y_test = pd.read_hdf("filtered_y_test", "mat",encoding='utf-8')

        return np.array(X_train.values), np.array(Y_train.values), np.array(X_test.values), np.array(Y_test.values)

    original, retrofitted = datasets[dataset]
    print("Searching in")
    print(directory)
    print("for:", original, retrofitted)

    o = pd.read_hdf(directory + original, 'mat', encoding='utf-8')
    r = pd.read_hdf(directory + retrofitted, 'mat', encoding='utf-8')
    r_sub = r.loc[o.index.intersection(r.index), :]
    del r
    gc.collect()

    # Filter out words that have not changed too much.
    cns = []

    print(len(o.values))
    testindexes = []
    for i in range(len(o.values)):
        if i%100000==0 and i!=0:
            # break
            print(i)
        x = o.iloc[i,:]
        y = r_sub.iloc[i,:]
        cn = cosine_similarity(x, y)
        if cn<0.95:
            cns.append(i)
        else:
            testindexes.append(i)
    X_train = o.iloc[cns, :]
    Y_train = r_sub.iloc[cns, :]
    X_train.to_hdf("filtered_x", "mat")
    Y_train.to_hdf("filtered_y","mat")
    X_test = o.iloc[testindexes,:]
    Y_test = r_sub.iloc[testindexes,:]
    X_test.to_hdf("filtered_x_test", "mat")
    Y_test.to_hdf("filtered_y_test", "mat")
    return np.array(X_train.values),np.array(Y_train.values), np.array(X_test.values),np.array(Y_test.values)

def load_noisiest_words_dataset(dataset, seed=42, test_split=0.1, save_folder="./", cache=True, threshold = 0.95):
    global original, retrofitted
    if os.path.exists(os.path.join(save_folder,"filtered_x")) and os.path.exists(os.path.join(save_folder,"filtered_y"))\
            and cache:
        print("Reusing cache")
        X_train = pd.read_hdf(os.path.join(save_folder,"filtered_x"), 'mat', encoding='utf-8')
        Y_train = pd.read_hdf(os.path.join(save_folder,"filtered_y"),'mat',encoding='utf-8')
        # X_test = pd.read_hdf(os.path.join(save_folder,"filtered_x_test"), "mat",encoding='utf-8')
        # Y_test = pd.read_hdf(os.path.join(save_folder,"filtered_y_test"), "mat",encoding='utf-8')

        return np.array(X_train.values), np.array(Y_train.values)#, np.array(X_test.values), np.array(Y_test.values)

    original = dataset["original"]
    retrofitted = dataset["retrofitted"]
    directory = dataset["directory"]
    print("Searching")
    print("for:", original, retrofitted)

    o = pd.read_hdf(directory + original, 'mat', encoding='utf-8')
    r = pd.read_hdf(directory + retrofitted, 'mat', encoding='utf-8')
    r_sub = r.loc[o.index.intersection(r.index), :]
    del r
    gc.collect()

    # Filter out words that have not changed too much.
    cns = []

    def dot_product2(v1, v2):
        return sum(map(operator.mul, v1, v2))

    def vector_cos5(v1, v2):
        prod = dot_product2(v1, v2)
        len1 = math.sqrt(dot_product2(v1, v1))
        len2 = math.sqrt(dot_product2(v2, v2))
        if len1*len2==0:
            return prod/((len1*len2)+1)
        return prod / (len1 * len2)

    print(len(o.values))
    testindexes = []
    tot = 0
    it = 0
    for i in range(len(o.values)):
        if i%10000==0 and i!=0:
            print(len(cns),len(testindexes))
            print(i)
        x = o.iloc[i,:]
        y = r_sub.iloc[i,:]
        cn = cosine_similarity(x, y)
        tot+=cn
        it+=1
        if cn<threshold:
            cns.append(i)
        else:
            testindexes.append(i)
    print("avg",tot/it)
    X_train = o.iloc[cns, :]
    Y_train = r_sub.iloc[cns, :]
    print("Dumping training")
    X_train.to_hdf(os.path.join(save_folder,"filtered_x"), "mat")
    Y_train.to_hdf(os.path.join(save_folder,"filtered_y"),"mat")
    X_test = o.iloc[testindexes,:]
    Y_test = r_sub.iloc[testindexes,:]
    print("Dumping testing")
    X_test.to_hdf(os.path.join(save_folder,"filtered_x_test"), "mat")
    Y_test.to_hdf(os.path.join(save_folder,"filtered_y_test"), "mat")
    print("Returning")
    return np.array(X_train.values),np.array(Y_train.values)#, np.array(X_test.values),np.array(Y_test.values)


def load_training_input_2(limit=10000,normalize=True, seed = 42,test_split=0.1):
    global common_retro_vectors_train,common_retro_vectors_test,common_vectors_test,common_vectors_train
    words, vectors = load_embedding("retrogan/wiki-news-300d-1M-subword.vec",limit=limit)
    retrowords, retrovectors =load_embedding("retrogan/numberbatch",limit=limit)
    print(len(words),len(retrowords))
    # common_vocabulary = set(words).intersection(set(retrowords))
    worddict = {}
    for idx, word in enumerate(retrowords):
        worddict[word] = (-1, idx)
    for idx, word in enumerate(words):
        try:
            # try to access and save the index
            retr_idx = worddict[word][1]
            worddict[word] = (idx, retr_idx)
        except:
            # not there so skip
            pass
    common_vocabulary = []
    common_retro_vectors = []
    common_vectors = []
    p = Pool(multiprocessing.cpu_count(),)
    for word in worddict.keys():
        if worddict[word][0] >= 0:
            common_vocabulary.append(word)
            common_retro_vectors.append(retrovectors[worddict[word][1]])
            common_vectors.append(vectors[worddict[word][0]])
    common_vectors = np.array(common_vectors)
    common_retro_vectors = np.array(common_retro_vectors)
    common_vocabulary = np.array(common_vocabulary)
    # common_vocabulary = np.array(list(common_vocabulary))
    # common_retro_vectors = np.array([retrovectors[retrowords.index(word)]for word in common_vocabulary])
    # common_vectors = np.array([vectors[words.index(word)]for word in common_vocabulary])
    if normalize:
        scaler = MinMaxScaler()
        scaler = scaler.fit(common_vectors)
        scaled_common_vector = scaler.transform(common_vectors)

        scaler = MinMaxScaler()
        scaler = scaler.fit(common_retro_vectors)
        scaled_common_retro_vector = scaler.transform(common_retro_vectors)
    else:
        scaled_common_vector = common_vectors
        scaled_common_retro_vector = common_retro_vectors

    X_train, X_test, y_train, y_test = train_test_split(scaled_common_vector, scaled_common_retro_vector, test_size = test_split, random_state = seed)
    common_vectors_train = X_train
    common_retro_vectors_train = y_train
    common_vectors_test = X_test
    common_retro_vectors_test = y_test
    del retrowords,retrovectors,words,vectors
    gc.collect()
    print("Size of common vocabulary:"+str(len(common_vocabulary)))
    return common_vectors_train,common_retro_vectors_train,common_vectors_test,common_retro_vectors_test


def find_word(word,retro=True):
    retrowords,retrovectors = None,None
    if retro:
        retrowords, retrovectors =load_embedding("retrogan/numberbatch",limit=10000000,cache='./numberbatch')
    else:
        retrowords, retrovectors =load_embedding("retrogan/wiki-news-300d-1M-subword.vec",limit=10000000, cache='./fasttext')
    for idx, retrovector in enumerate(retrovectors):
        if np.array_equal(word,retrovector):
            print("Found word is ",retrowords[idx])
            del retrowords, retrovectors
            return
    del retrowords, retrovectors
    print("Word not found...")


def find_cross_closest(vec1, vec2, n_top, closest=0,verbose=False):
    #TODO SKIP THE NEIGHBORS OF THE ONE WE DO NOT COMPARE AGAINST
    results = []
    if closest == 0:
        #explore the dot between vec1 and synonyms of vec2
        closest_words, closest_vecs = find_closest_2(vec2,n_top=n_top,dataset='numberbatch')
        results = [(idx, item) for idx, item in enumerate(
            list(map(lambda x: cosine_similarity( np.array(x).reshape(1, dimensionality), np.array(vec1).reshape(1, dimensionality))[0][0], closest_vecs)))]
    else:
        #explore the dot between vec2 and synonyms of vec1
        closest_words, closest_vecs = find_closest_2(vec1,n_top=n_top,dataset='numberbatch')
        results = [(idx, item) for idx, item in enumerate(
            list(map(lambda x: cosine_similarity(np.array(x).reshape(1, dimensionality), np.array(vec2).reshape(1, dimensionality))[0][0], closest_vecs)))]
    sorted_results = sorted(results, key=lambda x: x[1], reverse=True)
    final_n_results = []
    final_n_results_words = []
    final_n_results_weights = []
    for i in range(len(sorted_results)):
        if len(final_n_results)==n_top:
            print("Full")
            break
        # i += skip
        if verbose:
            print(closest_words[sorted_results[i][0]], sorted_results[i][1])
        final_n_results_words.append(closest_words[sorted_results[i][0]])
        final_n_results.append(np.array(closest_vecs[sorted_results[i][0]]))
        final_n_results_weights.append(sorted_results[i][1])

    # return final_n_results_words,final_n_results,final_n_results_weights
    return final_n_results_words,final_n_results

def find_cross_closest_2(vec1, vec2, projection_count=10,projection_cloud_count=20,n_top=200 ,closest=0,verbose=False):
    #TODO SKIP THE NEIGHBORS OF THE ONE WE DO NOT COMPARE AGAINST
    results = []
    #find the projection of one concept unto the other
    if closest == 0:
        #explore the dot between vec1 and synonyms of vec2
        closest_words, closest_vecs = find_closest_2(vec2,n_top=n_top,dataset='numberbatch',keep_o=True)
        results = [(idx, item) for idx, item in enumerate(
            list(map(lambda x: cosine_similarity( np.array(x).reshape(1, 300), np.array(vec1).reshape(1, 300))[0][0], closest_vecs)))]
    else:
        #explore the dot between vec2 and synonyms of vec1
        closest_words, closest_vecs = find_closest_2(vec1,n_top=n_top,dataset='numberbatch',keep_o=True)
        results = [(idx, item) for idx, item in enumerate(
            list(map(lambda x: cosine_similarity(np.array(x).reshape(1, 300), np.array(vec2).reshape(1, 300))[0][0], closest_vecs)))]
    sorted_results = sorted(results, key=lambda x: x[1], reverse=True)

    final_n_results = []
    final_n_results_words = []
    final_n_results_weights = []
    print("Finding the cloud of concepts around the cross closest")
    for res_idx, res in enumerate(sorted_results):
        if res_idx>projection_count:
            break
        if closest_words[sorted_results[res_idx][0]] in final_n_results_words:
            projection_count+=1
            continue
        final_n_results_words.append(closest_words[sorted_results[res_idx][0]])
        final_n_results.append(np.array(closest_vecs[sorted_results[res_idx][0]]))
        # now add the ones around that
        fin_aroud_vec = np.array(closest_vecs[sorted_results[res_idx][0]])
        #the projection cloud
        projection_cloud_words, projection_cloud_vecs = find_closest_2(fin_aroud_vec, n_top=projection_cloud_count, dataset='numberbatch',keep_o=True)
        ordered_projection_results = [(idx, item) for idx, item in enumerate(
            list(map(lambda x: cosine_similarity(np.array(x).reshape(1, 300), fin_aroud_vec.reshape(1, 300))[0][0],
                     projection_cloud_vecs)))]
        for pcres_idx, pcres in enumerate(ordered_projection_results):
            print("Working in",closest_words[sorted_results[res_idx][0]],res, "Cloud concept",closest_words[ordered_projection_results[pcres_idx][0]],pcres)
            if closest_words[ordered_projection_results[pcres_idx][0]] not in final_n_results_words:
                final_n_results_words.append(closest_words[ordered_projection_results[pcres_idx][0]])
                final_n_results.append(np.array(closest_vecs[ordered_projection_results[pcres_idx][0]]))
    if verbose: print("Finally",final_n_results_words)

    # return final_n_results_words,final_n_results,final_n_results_weights
    return final_n_results_words,final_n_results


def find_closest(pred_y,n_top=5,retro=True,skip=0,retrowords=None,retrovectors=None):
    if not (retrovectors is not None and retrowords is not None):
        if retro:
            retrowords, retrovectors =load_embedding("retrogan/numberbatch",limit=10000000)
        else:
            retrowords, retrovectors =load_embedding("retrogan/wiki-news-300d-1M-subword.vec",limit=10000000)
    # t1 = retrovectors[0].reshape(1,300)
    # t2 = pred_y.reshape(1,300)
    # res = cosine_similarity(t1,t2)
    results = [(idx,item) for idx,item in enumerate(list(map(lambda x: cosine_similarity(x.reshape(1,dimensionality), pred_y.reshape(1,dimensionality))[0][0],retrovectors)))]
    sorted_results = sorted(results,key=lambda x:x[1],reverse=True)
    final_n_results = []
    final_n_results_words = []
    for i in range(n_top):
        i += skip
        print(retrowords[sorted_results[i][0]],sorted_results[i][1])
        final_n_results_words.append(retrowords[sorted_results[i][0]])
        final_n_results.append(retrovectors[sorted_results[i][0]])

    del retrowords,retrovectors,results,sorted_results
    gc.collect()
    return final_n_results_words,final_n_results

o = None
dimensionality = 768
def find_closest_2(pred_y,n_top=5,retro=True,skip=0,verbose=True
                   , dataset="fasttext", keep_o=False):
    original, retrofitted = datasets[dataset]
    if keep_o:
        global o
        if o is None:
            print("Loading")
            o = pd.read_hdf(directory + retrofitted, 'mat', encoding='utf-8')
            print("Filtering")
            o = o.loc[[x for x in o.index if '/c/en/' in x and "." not in x],:]
            print("Done")
    else:
        print("Loading")
        o = pd.read_hdf(directory + retrofitted, 'mat', encoding='utf-8')
        print("Filtering")
        o = o.loc[[x for x in o.index if '/c/en/' in x and "." not in x], :]
        print("Done")
    # print(o)
    results = [(idx,item) for idx,item in enumerate(list(map(lambda x: cosine_similarity(x.reshape(1,dimensionality), pred_y.reshape(1,dimensionality)),np.array(o.iloc[:,:]))))]
    sorted_results = sorted(results,key=lambda x:x[1],reverse=True)
    final_n_results = []
    final_n_results_words = []
    final_n_results_weights = []
    for i in range(n_top):
        if i<skip:
            continue
        # i += skip
        if(verbose):
            print(o.index[sorted_results[i][0]])
        final_n_results_words.append(o.index[sorted_results[i][0]]) # the index
        final_n_results.append(o.iloc[sorted_results[i][0],:]) # the vector
        final_n_results_weights.append(sorted_results[i][1])
    del results,sorted_results
    if not keep_o:
        del o
    gc.collect()
    # return final_n_results_words,final_n_results,final_n_results_weights
    return final_n_results_words,final_n_results

def find_closest_in_dataset(pred_y,dataset, n_top=5,verbose=True,limit=None):
    print("Finding closest")
    if type(dataset) is str:
        o = pd.read_hdf(dataset, 'mat', encoding='utf-8')
    elif type(dataset) is pd.DataFrame:
        o = dataset
    else:
        raise Exception("Neither string nor dataframe provided as dataset")
    if limit is None:
        results = [(idx,item) for idx,item in enumerate(list(map(lambda x: cosine_similarity(x.reshape(1,dimensionality),
                                                                                         pred_y.reshape(1,dimensionality)),
                                                             np.array(o.iloc[:,:])
                                                             )))]
    else:
        results = [(idx, item) for idx, item in enumerate(list(map(lambda x: cosine_similarity(x.reshape(1, dimensionality),
                                                                                               pred_y.reshape(1, dimensionality)),
                                                                   np.array(o.iloc[0:limit, :])
                                                                   )))]
    sorted_results = sorted(results,key=lambda x:x[1],reverse=True)
    final_n_results = []
    final_n_results_words = []
    for i in range(n_top):
        if(verbose):
            print(o.index[sorted_results[i][0]])
        final_n_results_words.append(o.index[sorted_results[i][0]]) # the index
        final_n_results.append(o.iloc[sorted_results[i][0],:]) # the vector

    del o,results,sorted_results
    gc.collect()
    return final_n_results_words,final_n_results




def find_in_fasttext(testwords,return_words=False, dataset="fasttext"):
    original,retrofitted = datasets[dataset]
    o = pd.read_hdf(directory + original, 'mat', encoding='utf-8')
    # r = pd.read_hdf(directory + retrofitted, 'mat', encoding='utf-8')
    asarray1 = np.array(o.loc[["/c/en/"+x for x in testwords], :])
    return asarray1

def find_in_retrofitted(testwords, return_words=False, dataset="fasttext"):
    # o = pd.read_hdf(directory + original, 'mat', encoding='utf-8')
    original,retrofitted = datasets[dataset]
    r = pd.read_hdf(directory + retrofitted, 'mat', encoding='utf-8')
    asarray1 = np.array(r.loc[["/c/en/" + x for x in testwords], :])
    return asarray1

def check_index_in_dataset(testwords, dataset):
    results = [True if standardized_concept_uri("en",word) in dataset.index else False for word in testwords]
    return results

ft_model = None
def generate_fastext_embedding(word,keep_model_in_memory=True):
    global ft_model
    standardized_form = standardized_concept_uri("en",word).replace("/c/en/","")
    if ft_model is None:
        ft_model = fastText.load_model("fasttext_model/cc.en.300.bin")
    wv = ft_model.get_word_vector(standardized_form)
    if not keep_model_in_memory:
        del ft_model
        ft_model=None
        gc.collect()
    return wv

def get_retrofitted_embedding(plain_embedding,retrogan_to_rfe_generator,dimensionality=300):
    re = np.array(retrogan_to_rfe_generator.predict(plain_embedding.reshape(1,dimensionality))).reshape((dimensionality,))
    return re


def find_in_dataset(testwords,dataset):
    read = False
    if type(dataset) is str:
        r = pd.read_hdf(dataset, 'mat', encoding='utf-8')
        read = True
    elif type(dataset) is pd.DataFrame:
        r = dataset
    else:
        raise Exception("Neither string nor dataframe provided as dataset")
    asarray1 = r.loc[[standardized_concept_uri('en',x) for x in testwords], :]
    # print(asarray1)
    asarray1 = np.array(asarray1)
    # print(asarray1)
    if read:
        del r
    gc.collect()
    return asarray1

