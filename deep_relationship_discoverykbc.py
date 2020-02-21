import csv
import pickle

import pandas as pd
import sklearn
from conceptnet5.vectors import standardized_concept_uri
# from keras.utils import plot_model
from tensorflow.python.keras.layers import Concatenate
from tensorflow_core.python.keras.saving.save import load_model
from tensorflow_core.python.keras.utils.vis_utils import plot_model

from failed_tests.retrogan_trainer_attractrepel import *

relations = ["/r/PartOf", "/r/IsA", "/r/HasA", "/r/UsedFor", "/r/CapableOf", "/r/Desires",
             "/r/AtLocation"
             , "/r/HasSubevent", "/r/HasFirstSubevent", "/r/HasLastSubevent", "/r/HasPrerequisite",
             "/r/HasProperty", "/r/MotivatedByGoal", "/r/ObstructedBy", "/r/CreatedBy", "/r/Synonym",
             "/r/Causes", "/r/Antonym", "/r/DistinctFrom", "/r/DerivedFrom", "/r/SymbolOf", "/r/DefinedAs",
             "/r/SimilarTo", "/r/Entails",
             "/r/MannerOf", "/r/RelatedTo",
             "/r/LocatedNear", "/r/HasContext", "/r/FormOf",  "/r/EtymologicallyRelatedTo",
             "/r/EtymologicallyDerivedFrom", "/r/CausesDesire", "/r/MadeOf", "/r/ReceivesAction", "/r/InstanceOf",
             "/r/NotDesires", "/r/NotUsedFor", "/r/NotCapableOf", "/r/NotHasProperty"]


def conv1d(layer_input, filters, f_size=6, strides=1, normalization=True):
    d = Conv1D(filters, f_size, strides=strides, activation="relu")(layer_input)
    return d


def create_model():
    # Input needs to be 2 word vectors
    wv1 = Input(shape=(300,), name="retro_word_1")
    wv2 = Input(shape=(300,), name="retro_word_2")
    expansion_size = 128
    filters = 8

    def create_word_input_abstraction(wv1):
        # Expand and contract the 2 word vectors
        wv1_expansion_1 = Dense(512)(wv1)
        wv1_expansion_1 = BatchNormalization()(wv1_expansion_1)
        # r_1 = Reshape((-1, 1))(wv1_expansion_1)
        # t1 = conv1d(r_1, filters, f_size=4)
        # f1 = MaxPooling1D(pool_size=4)(t1)
        # f1 = Flatten()(f1)
        # wv1_expansion_2 = attention(f1)
        wv1_expansion_2 = attention(wv1_expansion_1)
        wv1_expansion_3 = Dense(int(expansion_size / 4), activation='relu')(wv1_expansion_2)
        wv1_expansion_3 = BatchNormalization()(wv1_expansion_3)
        return wv1_expansion_3

    wv1_expansion_3 = create_word_input_abstraction(wv1)
    wv2_expansion_3 = create_word_input_abstraction(wv2)

    # Concatenate both expansions
    merge1 = Concatenate()([wv1_expansion_3, wv2_expansion_3])
    merge_expand = Dense(1024, activation='relu')(merge1)
    merge_expand = BatchNormalization()(merge_expand)
    # Add atention layer
    merge_attention = attention(merge_expand)
    attention_expand = Dense(1024, activation='relu')(merge_attention)
    attention_expand = BatchNormalization()(attention_expand)
    semi_final_layer = Dense(1024, activation='relu')(attention_expand)
    semi_final_layer = BatchNormalization()(semi_final_layer)
    common_layers_model = Model([wv1, wv2], semi_final_layer, name="Common layers")
    # common_optimizer = Adam(lr=0.000002)
    # common_layers_model.compile()
    # Output layer
    # amount_of_relations = len(relations)
    # One big layer
    # final = Dense(amount_of_relations)(semi_final_layer)
    # Many tasks
    task_layer_neurons = 512
    losses = []
    model_dict = {}
    # prob_model_dict = {}
    # FOR PICS
    model_outs = []
    for rel in relations:
        task_layer = Dense(task_layer_neurons, activation='relu')(semi_final_layer)
        task_layer = BatchNormalization()(task_layer)
        task_layer = attention(task_layer)
        task_layer = Dense(task_layer_neurons, activation='relu')(task_layer)
        task_layer = BatchNormalization()(task_layer)

        layer_name = rel.replace("/r/", "")
        loss = "mean_squared_error"
        losses.append(loss)

        out = Dense(1,name=layer_name)(task_layer)
        # probability = Dense(units=1, activation='sigmoid',name=layer_name+"_prob")(task_layer)
        # scaler = Dense(units=1)(Dropout(0.5)(task_layer))
        # scaled_out = Dense(1)(multiply([probability,scaler]))
        # out = multiply([scale, probability])
        # scale = ConstMultiplierLayer()(probability)

        model_outs.append(out)
        # drdp = Model([wv1, wv2], probability, name=layer_name + "probability")
        drd = Model([wv1, wv2], out, name=layer_name)
        optimizer = Adam()
        drd.compile(optimizer=optimizer, loss=[loss],metrics=['mse','mae', 'acc'])
        # drdp.compile(optimizer=optimizer, loss=[loss])
        # drdp.summary()
        drd.summary()
        plot_model(drd,show_shapes=True)
        model_dict[layer_name] = drd
        # prob_model_dict[layer_name] = drdp

    # plot_model(Model([wv1,wv2],model_outs,name="Deep_Relationship_Discovery"),show_shapes=True,to_file="DRD.png")
    # model_dict["common"]=common_layers_model
    common_layers_model.summary()
    return model_dict#, prob_model_dict


def train_on_assertions(model, data, epoch_amount=100, batch_size=32, save_folder="drd",cutoff=0.75):
    retrofitted_embeddings = pd.read_hdf(retroembeddings, "mat", encoding='utf-8')
    training_data_dict = {}
    training_func_dict = {}
    print("Amount of data:",len(data))
    for i in tqdm(range(len(data))):
        if i == 10000: break
        stuff = data.iloc[i]
        rel = stuff[0]
        if rel not in training_data_dict.keys():
            training_data_dict[rel] = []
        training_data_dict[rel].append(i)

    def load_batch(output_name):
        print("Loading batch for", output_name)
        l = len(training_data_dict[output_name])
        iterable = list(range(0, l))
        shuffle(iterable)
        for ndx in range(0, l, batch_size):
            try:
                ixs = iterable[ndx:min(ndx + batch_size, l)]
                x_1 = []
                x_2 = []
                y = []
                for ix in ixs:
                    try:
                        stuff = data.iloc[training_data_dict[output][ix]]
                        l1 = np.array(retrofitted_embeddings.loc[stuff[1]]).reshape(1,300)
                        l2 = np.array(retrofitted_embeddings.loc[stuff[2]]).reshape(1,300)
                        x_1.append(l1)
                        x_2.append(l2)
                        y.append(float(stuff[3]))
                    except Exception as e:
                        print(e)
                        continue
                # print(np.array(x_1),np.array(x_2),np.array(y))
                yield np.array(x_1), np.array(x_2), np.array(y)
            except Exception as e:
                # print(e)
                return False
        return True

    for epoch in tqdm(range(epoch_amount)):
        total_loss = []
        exclude = relations
        shuffle(exclude)

        for output in exclude:
            training_func_dict[output] = load_batch(output)
        window_loss = 0
        tasks_completed = {}
        for task in exclude:
            tasks_completed[task] = False
        iter = 1
        while True:
            for output in exclude:
                try:
                    x_1, x_2, y = training_func_dict[output].__next__()
                    # print(x_1.shape)
                    x_1 = x_1.reshape(x_1.shape[0],x_1.shape[-1])
                    # print(x_1.shape)
                    x_2 = x_2.reshape(x_2.shape[0], x_2.shape[-1])
                    loss = model[output.replace("/r/", "")].train_on_batch(x={'retro_word_1': x_1, 'retro_word_2': x_2},
                                                                           y=y)
                    total_loss.append(loss)
                    iter += 1
                except Exception as e:
                    # print("Error in", output, str(e))
                    print("In training error")
                    print(e)
                    if 'the label' not in str(e):
                        tasks_completed[output] = True

            # print(len([x for x in tasks_completed.values() if x]),"/", len(tasks_completed.values()))
            if len([x for x in tasks_completed.values() if x]) / len(tasks_completed.values()) > cutoff:
                break
            iter+=1
        print("Avg loss", total_loss)
        print(str(epoch) + "/" + str(epoch_amount))

        # for key in prob_model.keys():
        #     prob_model[key].save(save_folder + "/" + key + "probability.model")
            # exit()
        print("Testing")
        model_name = "PartOf"
        test_model(model, model_name=model_name)
        # test_model(prob_model, model_name=model_name)
    print("Saving...")
    try:
        os.mkdir(save_folder)
    except Exception as e:
        print(e)
    for key in model.keys():
        model[key].save(save_folder + "/" + key + ".model")
def create_data(use_cache=True):
    if os.path.exists("tmp/valid_rels.hd5") and use_cache:
        print("Using cache")
        return pd.read_hdf("tmp/valid_rels.hd5", "mat")
    assertionspath = "train600k.txt"
    valid_relations = []
    with open(assertionspath) as assertionsfile:
        assertions = csv.reader(assertionsfile, delimiter="\t")
        row_num = 0
        for assertion_row in assertions:
            row_num += 1
            # if row_num == 10000:
            #     break
            if row_num % 100000 == 0: print(row_num)
            try:
                weight = float(assertion_row[3])
                c1 = standardized_concept_uri("en",assertion_row[1])
                c2 = standardized_concept_uri("en",assertion_row[2])
                row = [assertion_row[0], c1, c2, weight]
                # print(row)
                valid_relations.append(row)
            except Exception as e:
                # print(e)
                pass
                # print(e)
            if len(valid_relations) % 10000 == 0:
                print(len(valid_relations))
    af = pd.DataFrame(data=valid_relations, index=range(len(valid_relations)))
    print("Training data:")
    print(af)
    af.to_hdf("tmp/valid_rels.hd5", "mat")
    return af
def create_test_data(use_cache=True):
    if os.path.exists("tmp/test_valid_rels.hd5") and use_cache:
        print("Using cache")
        return pd.read_hdf("tmp/test_valid_rels.hd5", "mat")
    assertionspath = "dev1.txt"
    valid_relations = []
    with open(assertionspath) as assertionsfile:
        assertions = csv.reader(assertionsfile, delimiter="\t")
        row_num = 0
        for assertion_row in assertions:
            row_num += 1
            if row_num % 100000 == 0: print(row_num)
            try:
                weight = float(assertion_row[3])
                c1 = standardized_concept_uri("en",assertion_row[1])
                c2 = standardized_concept_uri("en",assertion_row[2])
                row = [assertion_row[0], c1, c2, weight]
                # print(row)
                valid_relations.append(row)
            except Exception as e:
                # print(e)
                pass
                # print(e)
            if len(valid_relations) % 10000 == 0:
                print(len(valid_relations))
    af = pd.DataFrame(data=valid_relations, index=range(len(valid_relations)))
    print("Training data:")
    print(af)
    af.to_hdf("tmp/test_valid_rels.hd5", "mat")
    return af

def load_data(path):
    data = pd.read_hdf(path, "mat", encoding="utf-8")
    return data


def test_model(model_dict, model_name="all", normalizers=None):
    batch_size = 64
    def load_batch(output_name):
        print("Loading batch for", output_name)
        l = len(test_data[output_name])
        iterable = list(range(0, l))
        shuffle(iterable)
        for ndx in range(0, l, batch_size):
            try:
                ixs = iterable[ndx:min(ndx + batch_size, l)]
                x_1 = []
                x_2 = []
                y = []
                for ix in ixs:
                    try:
                        stuff = data.iloc[test_data[output][ix]]
                        l1 = np.array(retrofitted_embeddings.loc[stuff[1]]).reshape(1,300)
                        l2 = np.array(retrofitted_embeddings.loc[stuff[2]]).reshape(1,300)
                        x_1.append(l1)
                        x_2.append(l2)
                        y.append(float(stuff[3]))
                    except Exception as e:
                        # print(e)
                        continue
                # print(np.array(x_1),np.array(x_2),np.array(y))
                yield np.array(x_1), np.array(x_2), np.array(y)
            except Exception as e:
                # print(e)
                return False
        return True
    total_loss = []
    iter = 1
    exclude = relations
    shuffle(exclude)
    testing_func_dict = {}
    for output in exclude:
        testing_func_dict[output] = load_batch(output)
    window_loss = 0
    tasks_completed = {}
    for task in exclude:
        tasks_completed[task] = False
    iter = 1
    while True:
        for output in exclude:
            try:
                x_1, x_2, y = testing_func_dict[output].__next__()
                # print(x_1.shape)
                x_1 = x_1.reshape(x_1.shape[0], x_1.shape[-1])
                # print(x_1.shape)
                x_2 = x_2.reshape(x_2.shape[0], x_2.shape[-1])
                loss = model[output.replace("/r/", "")].test_on_batch(x={'retro_word_1': x_1, 'retro_word_2': x_2},
                                                                       y=y)
                print(loss)
                # loss_2 = model[output.replace("/r/", "")].train_on_batch(x={'retro_word_1':x_2,'retro_word_2':x_1},y=y)
                total_loss.append(loss)
                iter += 1
                # if loss > 10:
                #     print("Loss", output, loss)
                # if iter%100:
                #     print(loss)
            except Exception as e:
                # print("Error in", output, str(e))
                if 'the label' not in str(e):
                    tasks_completed[output] = True
                else:
                    print(e)
        # print(len([x for x in tasks_completed.values() if x]),"/", len(tasks_completed.values()))
        if len([x for x in tasks_completed.values() if x]) / len(tasks_completed.values())==1:
            break
        iter += 1
    print("Avg dev loss", total_loss )


def normalize_outputs(model, save_folder="./drd", use_cache=True):
    save_path = save_folder + "/" + "normalization_dict.pickle"
    if use_cache:
        try:
            norm_dict = pickle.load(open(save_path, 'rb'))
            return norm_dict
        except Exception as e:
            print(e)
            print("Cache not found")

    # Set up our variables
    normalization_dict = {}
    x1 = []
    x2 = []
    y = []

    # Load our data
    retrofitted_embeddings = pd.read_hdf(retroembeddings, "mat")
    rand_range = [x for x in range(len(retrofitted_embeddings.index))]
    shuffle(rand_range)

    for i in range(len(retrofitted_embeddings.index)):
        x1.append(np.array(retrofitted_embeddings.iloc[rand_range[i]]).reshape(1,300))
        x2.append(np.array(retrofitted_embeddings.iloc[i]).reshape(1, 300))
    for rel in relations:
        rel_normer = sklearn.preprocessing.MinMaxScaler().fit(
            model[rel.replace("/r/", "")].predict(x={"retro_word_1": np.array(x1).reshape(len(x1), 300),
                                                     "retro_word_2": np.array(x2).reshape(len(x1), 300)}))
        normalization_dict[rel.replace("/r/", "")] = rel_normer
        print(rel_normer)
    pickle.dump(normalization_dict, open(save_path, "wb"))
    return normalization_dict


def load_model_ours(save_folder="./drd", model_name="all",probability_models=False):
    model_dict = {}
    if model_name == 'all':
        for rel in relations:
            print("Loading", rel)
            layer_name = rel.replace("/r/", "")
            if probability_models:
                print("Loading",save_folder + "/" + layer_name + "probability.model")
                model_dict[layer_name] = load_model(save_folder + "/" + layer_name + "probability.model",
                                                    custom_objects={"ConstMultiplierLayer": ConstMultiplierLayer})
                model_dict[layer_name].summary()
            else:
                model_dict[layer_name] = load_model(save_folder + "/" + layer_name + ".model",
                                                    custom_objects={"ConstMultiplierLayer": ConstMultiplierLayer})

    else:
        layer_name = model_name.replace("/r/", "")
        if not probability_models:
            print("Loading models")
            model_dict[layer_name] = load_model(save_folder + "/" + layer_name + ".model",
                                                custom_objects={"ConstMultiplierLayer": ConstMultiplierLayer})
            print("Loading weights")
            model_dict[layer_name].load_weights(save_folder + "/" + layer_name + ".model")
        else:
            print("Loading models")
            model_dict[layer_name] = load_model(save_folder + "/" + layer_name + "probability.model",
                                                custom_objects={"ConstMultiplierLayer": ConstMultiplierLayer})
            print("Loading weights")
            model_dict[layer_name].load_weights(save_folder + "/" + layer_name + "probability.model")

    # model_dict["common"] = load_model(save_folder + "/" + "common" + ".model",
    #                                         custom_objects={"ConstMultiplierLayer": ConstMultiplierLayer})
    return model_dict

# retroembeddings = "trained_models/retroembeddings/2019-04-0813:03:02.430691/retroembeddings.h5"
# retroembeddings = "trained_models/retroembeddings/2019-10-22 11:57:48.878874/retroembeddings.h5"
# retroembeddings = "trained_models/retroembeddings/2019-05-15 11:47:52.802481/retroembeddings.h5"
retroembeddings = "fasttext_model/attract_repel.hd5clean"
if __name__ == '__main__':
    # # save_folder =     "./trained_models/deepreldis/"+str(datetime.datetime.now())
    retrofitted_embeddings = pd.read_hdf(retroembeddings, "mat")
    global w1, w2, w3
    w1 = np.array(retrofitted_embeddings.loc[standardized_concept_uri("en", "building")]).reshape(1, 300)
    w2 = np.array(retrofitted_embeddings.loc[standardized_concept_uri("en", "photography")]).reshape(1, 300)
    w3 = np.array(retrofitted_embeddings.loc[standardized_concept_uri("en", "surfing")]).reshape(1, 300)
    model_name = "UsedFor"
    os.makedirs("tmp",exist_ok=True)

    # remove_r = True
    # if remove_r:
    #     print("Removing /r/ from relations")
    #     relations = [x.replace("/r/","") for x in relations]
    # del retrofitted_embeddings
    # gc.collect()
    print("Done\nLoading data")
    # model = load_model_ours()
    print("Converting to our format")
    data = create_data(use_cache=True)
    global test_data
    test_data = create_test_data()
    relations = list(set(data.iloc[:,0]))
    print("Creating model...")
    model = create_model()

    # print(s1)
    # print(s2)
    # print(s2.difference(s1))
    # # data = load_data("valid_rels.hd5")
    print("Done\nTraining")
    train_on_assertions(model, data,save_folder="trained_models/deepreldis/"+str(datetime.datetime.now())+"/",epoch_amount=10000,batch_size=32)
    print("Done\n")
    # model = load_model_ours(save_folder="trained_models/deepreldis/2019-05-28",model_name=model_name)
    # model = load_model_ours(save_folder="trained_models/deepreldis/2019-04-25_2_sigmoid",model_name=model_name,probability_models=True)
    normalizers = normalize_outputs(model,use_cache=False)
    # normalizers = normalize_outputs(model,use_cache=False)
    test_model(model, normalizers=normalizers, model_name=model_name)
    # Output needs to be the relationship weights
