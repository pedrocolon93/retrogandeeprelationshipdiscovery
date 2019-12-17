from __future__ import print_function, division

import datetime
import math
import os
import random
import shutil
from random import shuffle
from time import sleep

import numpy as np
# from tensorflow_core.python.keras import backend as K
from numpy.random import seed
from tensorflow.keras import backend as K
from tensorflow import keras
from tensorflow.python.eager import *
from tensorflow.python.keras.layers import Input, Layer, Conv1D, Dense, multiply, add, BatchNormalization, \
    MaxPooling1D, Flatten, Dropout, LeakyReLU, GaussianNoise
from tensorflow.python.keras import Model
from tensorflow.python.framework.ops import disable_eager_execution
# from tensorflow_core.python.framework.random_seed import set_random_seed
# from tensorflow_core.python.keras.optimizer_v2.adam import Adam
# from tensorflow_core.python.keras.optimizer_v2.rmsprop import RMSProp
# from tensorflow_core.python.keras.optimizer_v2
# from tensorflow_core.python.keras.utils.vis_utils import plot_model
# from tensorflow_core.python.keras.optimizers import Adadelta
from tensorflow_core.python.keras.optimizer_v2.rmsprop import RMSProp
from tqdm import tqdm
import tensorflow as tf

# tf.debugging.set_log_device_placement(True)

import tools

# seed(1)
#
# set_random_seed(2)
# os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
from adabound import AdaBound

shutil.rmtree("./logs",ignore_errors=True)
print("Removing logs and sleeping for a few seconds")
sleep(5)

def write_log(callback, names, logs, batch_no):
    for name, value in zip(names, logs):
        summary = tf.compat.v1.summary.Summary()
        summary_value = summary.value.add()
        summary_value.simple_value = value
        summary_value.tag = name
        callback.writer.add_summary(summary, batch_no)
        callback.writer.flush()


class ConstMultiplierLayer(Layer):
    def __init__(self, **kwargs):
        super(ConstMultiplierLayer, self).__init__(**kwargs)

    def build(self, input_shape):
        self.k = self.add_weight(
            name='k',
            shape=(),
            initializer='zeros',
            dtype='float32',
            trainable=True,
        )
        super(ConstMultiplierLayer, self).build(input_shape)

    def call(self, x, **kwargs):
        return tf.math.multiply(self.k, x)

    def compute_output_shape(self, input_shape):
        return input_shape


def attention(layer_input, amount=None):
    # ATTENTION PART STARTS HERE
    if amount is not None:
        attention_probs = Dense(amount[1], activation='softmax')(layer_input)
    else:
        sh = tf.keras.backend.int_shape(layer_input)
        attention_probs = Dense(sh[1], activation='softmax')(layer_input)
    attention_mul = multiply([layer_input, attention_probs]
                             )
    attention_scale = ConstMultiplierLayer()(attention_mul)
    attention = add([layer_input, attention_scale])
    # ATTENTION PART FINISHES HERE
    return attention


class RetroCycleGAN():
    def __init__(self, save_index="0", save_folder="./", generator_size=32,
                 discriminator_size=64, word_vector_dimensions=300,
                 discriminator_lr=0.0001, generator_lr=0.0005,
                 lambda_cycle=3, lambda_id_weight=0.3,
                 clip_value=0.5, optimizer="sgd", batch_size=32):
        # @tf.function

        self.save_folder = save_folder

        # Input shape
        self.word_vector_dimensions = word_vector_dimensions
        self.img_shape = (self.word_vector_dimensions,)  # , self.channels)
        self.save_index = save_index

        # Number of filters in the first layer of G and D
        self.gf = generator_size
        self.df = discriminator_size

        # Loss weights
        self.lambda_cycle = lambda_cycle  # Cycle-consistency loss
        self.lambda_id = lambda_id_weight = 0 # Identity loss

        d_lr = discriminator_lr
        self.d_lr = d_lr
        g_lr = generator_lr
        self.g_lr = g_lr
        # cv = clip_value
        # cn = cn
        self.d_A = self.build_discriminator(name="word_vector_discriminator")
        self.d_B = self.build_discriminator(name="retrofitted_word_vector_discriminator")
        # Best combo sofar SGD, gaussian, dropout,5,0.5 mml(0,5,.5),3x1024gen, 2x1024, no normalization

        # return Adam(lr,amsgrad=True,decay=1e-8)

        # -------------------------
        # Construct Computational
        #   Graph of Generators
        # -------------------------

        # Build the generators
        self.g_AB = self.build_generator(name="to_retro_generator")

        # self.d_A.summary()
        # self.g_AB.summary()
        # plot_model(self.g_AB, show_shapes=True)
        self.g_BA = self.build_generator(name="from_retro_generator")

        # self.d_B.summary()
        # self.g_BA.summary()
        # Input images from both domains
        unfit_wv = Input(shape=self.img_shape, name="plain_word_vector")
        fit_wv = Input(shape=self.img_shape, name="retrofitted_word_vector")

        # Translate images to the other domain
        fake_B = self.g_AB(unfit_wv)
        fake_A = self.g_BA(fit_wv)
        # Translate images back to original domain
        reconstr_A = self.g_BA(fake_B)
        reconstr_B = self.g_AB(fake_A)
        # Identity mapping of images
        # unfit_wv_id = self.g_BA(unfit_wv)
        # fit_wv_id = self.g_AB(fit_wv)
        unfit_wv_mm = self.g_AB(unfit_wv)
        fit_wv_mm = self.g_BA(fit_wv)

        # For the combined model we will only train the generators
        self.d_A.trainable = False
        self.d_B.trainable = False

        # Discriminators determines validity of translated images
        valid_A = self.d_A(fake_A)
        valid_B = self.d_B(fake_B)

        # Combined model trains generators to fool discriminators
        self.combined = Model(inputs=[unfit_wv, fit_wv],
                              outputs=[valid_A, valid_B,
                                       reconstr_A, reconstr_B,
                                       unfit_wv_mm, fit_wv_mm],
                              name="combinedmodel")

        log_path = './logs'
        callback = keras.callbacks.TensorBoard(log_dir=log_path)
        callback.set_model(self.combined)
        self.combined_callback = callback

        # plot_model(self.combined, to_file="RetroGAN.png", show_shapes=True)

    def compile_all(self, optimizer="sgd"):
        def max_margin_loss(y_true, y_pred):
            cost = 0
            sim_neg = 25
            sim_margin = 1
            for i in range(0, sim_neg):
                new_true = tf.random.shuffle(y_true)
                normalize_a = tf.nn.l2_normalize(y_true)
                normalize_b = tf.nn.l2_normalize(y_pred)
                normalize_c = tf.nn.l2_normalize(new_true)
                minimize = tf.reduce_sum(tf.multiply(normalize_a, normalize_b))
                maximize = tf.reduce_sum(tf.multiply(normalize_c, normalize_b))
                mg = sim_margin - minimize + maximize
                # cost += mg
                cost += tf.keras.backend.clip(mg, 0, 10000)
                # cost += tf.clip_by_value(mg, min=0)
            return cost / (sim_neg * 1.0)

        def create_opt(lr=0.1):
            if optimizer == "sgd":
                return tf.optimizers.SGD(lr=lr, momentum=0.9,decay=1/(1000*750))
            elif optimizer == "adam":
                return tf.optimizers.Adam()
            elif optimizer == "adabound":
                return AdaBound(lr=1e-04,
                                final_learning_rate=0.05,
                                gamma=1e-05,
                                weight_decay=0.,
                                amsbound=False,
                                epsilon=1e-8)
            elif optimizer == "nadam":
                return tf.optimizers.Nadam()
            elif optimizer == "rmsprop":
                return RMSProp()
            elif optimizer == "adadelta":
                return tf.optimizers.Adadelta(lr=lr)
            else:
                raise KeyError("coULD NOT FIND THE OPTIMIZER")

        self.d_A.compile(loss='binary_crossentropy',
                         optimizer=create_opt(self.d_lr),
                         metrics=['accuracy'])
        self.d_B.compile(loss='binary_crossentropy',
                         optimizer=create_opt(self.d_lr),
                         metrics=['accuracy'])
        self.g_AB.compile(loss=max_margin_loss,
                          optimizer=create_opt(self.g_lr),
                          )
        self.g_BA.compile(loss=max_margin_loss,
                          optimizer=create_opt(self.g_lr),
                          )
        self.combined.compile(loss=['binary_crossentropy', 'binary_crossentropy',
                                    'mse', 'mse',
                                    max_margin_loss, max_margin_loss],
                              loss_weights=[1, 1,
                                            1, 1,
                                            1, 1
                                            ],
                              # TODO ADD A CUSTOM LOSS THAT SIMPLY ADDS A
                              # GENERALIZATION CONSTRAINT ON THE MAE
                              optimizer=create_opt(self.g_lr))
        # self.combined.summary()

    def build_generator(self, name):
        """U-Net Generator"""

        def dense(layer_input, filters, f_size=6, normalization=True, dropout=True):
            """Layers used during downsampling"""
            # d = BatchNormalization()(layer_input)
            d = Dense(filters, activation="relu")(layer_input)
            # d = LeakyReLU(alpha=0.2)(d)
            if normalization:
                d = BatchNormalization()(d)
            if dropout:
                d = Dropout(0.2)(d)
            return d

        def conv1d(layer_input, filters, f_size=6, strides=1, normalization=True):
            d = Conv1D(filters, f_size, strides=strides, activation="relu")(layer_input)

            return d

        # def deconv1d(layer_input, filters, f_size=6, strides=1, normalization=True):
        #     d = UpSampling1D(filters, f_size, strides=strides, activation="relu")(layer_input)
        #     return d

        # Image input
        inpt = Input(shape=self.img_shape)
        # Continue into fc layers
        d0 = dense(inpt, 2048, normalization=True)
        d0 = dense(d0, 2048, normalization=True)
        d0 = dense(d0, 2048, normalization=True)
        # d0 = dense(d0, 1024, normalization=True)
        # d0 = dense(d0, 2048, normalization=True)

        # r = tf.compat.v2.keras.layers.Reshape((d0.get_shape()[-1], 1))(d0)
        # # # Downscaling
        # # t1 = conv1d(r,self.gf*8,f_size=6)
        # t2 = conv1d(r, 2048, f_size=8)
        # t2 = conv1d(r, 128, f_size=4)
        # # # t3 = conv1d(t2, self.gf, f_size=4)
        # f = MaxPooling1D()(t2)
        # f = Flatten()(f)
        # f = tf.compat.v1.keras.layers.Reshape((-1))(f)
        # # att
        # # if tf.keras.backend.int_shape(f)[1] is None:
        # #
        # #     shape_flatten = np.prod(shape_before_flatten)  # value of shape in the non-batch dimension
        # attn = attention(f)
        # # else:
        # attn = attention(d0)

        # VAE Like layer
        # latent_dim = 128
        # z_mean = Dense(latent_dim,
        #                     name='z_mean')(d2)
        # z_log_var = Dense(latent_dim,
        #                        name='z_log_var')(d2)
        #
        # # use reparameterization trick to push the sampling out as input
        # # note that "output_shape" isn't necessary with the TensorFlow backend
        # z = Lambda(sampling, output_shape=(latent_dim,), name='z')([z_mean, z_log_var])

        # Last 2 fc layers
        # Maybe attention
        # r = Reshape((-1, 1))(attn)
        # # Downscaling
        # t4 = conv1d(r, self.gf, f_size=4)
        # t5 = conv1d(t4, self.gf *2, f_size=4)
        # f = Flatten()(t5)
        # f = UpSampling1D(size=2)(t5)
        # d4 = dense(d0, 2048)
        output_img = Dense(dimensionality)(d0)
        return Model(inpt, output_img, name=name)

    def build_discriminator(self, name):

        def d_layer(layer_input, filters, f_size=7, normalization=True, dropout=True):
            """Discriminator layer"""
            d = Dense(filters, activation="relu")(layer_input)
            # d = LeakyReLU(alpha=0.2)(d)
            if normalization:
                d = BatchNormalization()(d)
            if dropout:
                d = Dropout(0.5)(d)
            # d = GaussianNoise(0.1)(d)
            return d

        inpt = Input(shape=self.img_shape)
        # noise = GaussianNoise(0.01)(inpt)
        d1 = d_layer(inpt, 2048, normalization=True, dropout=True)
        d1 = d_layer(d1, 2048, normalization=True, dropout=True)
        # d1 = d_layer(d1, 2048,normalization=False)
        # d2 = d_layer(d1, self.df * 8)
        # # d2 = attention(d2)
        validity = Dense(1, activation="sigmoid")(d1)
        return Model(inpt, validity, name=name)

    def load_weights(self, preface="", folder=None):
        if folder is None:
            folder = self.save_folder
        try:
            self.g_AB.reset_states()
            self.g_BA.reset_states()
            self.combined.reset_states()
            self.d_B.reset_states()
            self.d_A.reset_states()
            self.d_A.load_weights(os.path.join(folder, preface + "fromretrodis.h5"))
            self.d_B.load_weights(os.path.join(folder, preface + "toretrodis.h5"))
            self.g_AB.load_weights(os.path.join(folder, preface + "toretrogen.h5"))
            self.g_BA.load_weights(os.path.join(folder, preface + "fromretrogen.h5"))
            self.combined.load_weights(os.path.join(folder, preface + "combined_model.h5"))

        except Exception as e:
            print(e)

    def train(self, epochs, dataset, batch_size=1, pretraining_epochs=150, rc=None):
        start_time = datetime.datetime.now()
        res = []
        X_train = Y_train = None
        X_train, Y_train = tools.load_all_words_dataset_3(dataset,
                                                          save_folder="adversarial_paper_data/",
                                                          threshold=0.90,
                                                          cache=False,
                                                          remove_constraint=rc)
        print("Done")

        # X_train, Y_train, X_test, Y_test = load_training_input_3(seed=seed,test_split=0.001,dataset=dataset)

        # def load_batch(batch_size=32):
        #     l = X_train.shape[0]
        #     iterable = list(range(0, l))
        #     shuffle(iterable)
        #     for ndx in tqdm(range(0, l, batch_size), ncols=30):
        #         ixs = iterable[ndx:min(ndx + batch_size, l)]
        #         imgs_A = X_train[ixs]
        #         imgs_B = Y_train[ixs]
        #         yield imgs_A, imgs_B
        def load_batch(batch_size=32, always_random=False):
            iterable = list(X_train.index)
            shuffle(iterable)
            batches = []
            print("Prefetching batches")
            for ndx in tqdm(range(0, len(iterable), batch_size), ncols=30):
                ixs = iterable[ndx:min(ndx + batch_size, len(iterable))]
                if always_random:
                    ixs = list(np.array(iterable)[random.sample(range(0, len(iterable)), batch_size)])
                imgs_A = X_train.loc[ixs]
                imgs_B = Y_train.loc[ixs]
                batches.append((imgs_A, imgs_B))
            print("Begginging iteration")
            for i in tqdm(range(0, len(batches)), ncols=30):
                imgs_A, imgs_B = batches[i]
                yield imgs_A, imgs_B

        # def load_batch(batch_size=2,batch_amount=1000000):
        #     l = X_train.shape[0]
        #     iterable = list(range(0, l))
        #     shuffle(iterable)
        #     # for ndx in tqdm(range(0, l, batch_size), ncols=30):
        #     for i in tqdm(range(batch_amount)):
        #         ixs = random.sample(range(0,len(iterable)), batch_size)
        #         imgs_A = X_train[ixs]
        #         imgs_B = Y_train[ixs]
        #         yield imgs_A, imgs_B

        # def load_random_batch(batch_size=2,batch_amount=1000000):
        #     iterable = list(X_train.index)
        #     # shuffle(iterable)
        #     for i in tqdm(range(batch_amount)):
        #         ixs = random.sample(range(0,len(iterable)), batch_size)
        #         fixs = np.array(iterable)[ixs]
        #         imgs_A = X_train.loc[fixs]
        #         imgs_B = Y_train.loc[fixs]
        #         yield imgs_A, imgs_B
        def load_random_batch(batch_size=32, batch_amount=1000000):
            iterable = list(X_train.index)
            # shuffle(iterable)
            ixs = random.sample(range(0, len(iterable)), batch_size)
            fixs = np.array(iterable)[ixs]
            imgs_A = X_train.loc[fixs]
            imgs_B = Y_train.loc[fixs]
            return imgs_A, imgs_B

        # os.path.join(final_save_folder, str(idx))

        def exp_decay(epoch):
            initial_lrate = 0.1
            k = 0.1
            lrate = initial_lrate * math.exp(-k * epoch)
            return lrate

        noise = np.random.normal(size=(batch_size, dimensionality), scale=0.01)
        dis_train_amount = 2.0

        self.compile_all("adam")

        def train_(training_epochs, always_random=False):
            for epoch in range(training_epochs):
                for batch_i, (imgs_A, imgs_B) in enumerate(load_batch(batch_size, always_random=always_random)):
                    fake_B = self.g_AB.predict(imgs_A)
                    fake_A = self.g_BA.predict(imgs_B)
                    # Train the discriminators (original images = real / translated = Fake)
                    dA_loss = None
                    dB_loss = None
                    valid = np.ones((imgs_A.shape[0],))  # *noisy_entries_num,) )
                    fake = np.zeros((imgs_A.shape[0],))  # *noisy_entries_num,) )

                    for i in range(int(dis_train_amount)):
                        nimgs_A = imgs_A
                        nimgs_B = imgs_B
                        # if i % 2 == 0:
                        #     print("Adding noise")
                        #     nimgs_A = np.add(noise[0:imgs_A.shape[0], :], imgs_A)
                        #     nimgs_B = np.add(noise[0:imgs_B.shape[0], :], imgs_B)

                        dA_loss_real = self.d_A.train_on_batch(nimgs_A, valid)
                        dA_loss_fake = self.d_A.train_on_batch(fake_A, fake)
                        if dA_loss is None:
                            dA_loss = 0.5 * np.add(dA_loss_real, dA_loss_fake)
                        else:
                            dA_loss += 0.5 * np.add(dA_loss_real, dA_loss_fake)

                        dB_loss_real = self.d_B.train_on_batch(nimgs_B, valid)
                        dB_loss_fake = self.d_B.train_on_batch(fake_B, fake)
                        if dB_loss is None:
                            dB_loss = 0.5 * np.add(dB_loss_real, dB_loss_fake)
                        else:
                            dB_loss += 0.5 * np.add(dB_loss_real, dB_loss_fake)
                    d_loss = 0.5 * np.add(dA_loss / dis_train_amount, dB_loss / dis_train_amount)
                    # Total disciminator loss
                    # ------------------
                    #  Train Generators
                    # ------------------
                    # Train the generators
                    rand_a, rand_b = load_random_batch(imgs_A.shape[0])
                    # mm_a_loss = self.g_AB.train_on_batch(rand_a, rand_b)
                    # mm_b_loss = self.g_BA.train_on_batch(rand_b, rand_a)
                    mm_a_loss = 0
                    mm_b_loss = 0

                    g_loss = self.combined.train_on_batch([imgs_A, imgs_B],
                                                          [valid, valid,
                                                           imgs_A, imgs_B,
                                                           imgs_A, imgs_B])

                    def named_logs(model, logs):
                        result = {}
                        for l in zip(model.metrics_names, logs):
                            result[l[0]] = l[1]
                        return result

                    self.combined_callback.on_epoch_end(batch_i, named_logs(self.combined, g_loss))
                    # profiler_result = profiler.stop()
                    # profiler.save("./logs", profiler_result)
                    elapsed_time = datetime.datetime.now() - start_time
                    if batch_i % 50 == 0:
                        print(
                            "\n[Epoch %d/%d] [Batch %d] [D loss: %f, acc: %3d%%] [G loss: %05f, adv: %05f, recon: %05f, id: %05f][mma:%05f,mmb:%05f]time: %s " \
                            % (epoch, training_epochs,
                               batch_i,
                               d_loss[0], 100 * d_loss[1],
                               g_loss[0],
                               np.mean(g_loss[1:3]),
                               np.mean(g_loss[3:5]),
                               np.mean(g_loss[5:6]),
                               mm_a_loss,
                               mm_b_loss,
                               elapsed_time))
                try:
                    if epoch % 5 == 0:
                        self.save_model(name=str(epoch))
                        # self.save_model()
                    print("\n")
                    sl = tools.test_sem(rcgan.g_AB, dataset, dataset_location="testing/SimLex-999.txt",
                                        fast_text_location="fasttext_model/cc.en.300.bin")[0]
                    sv = tools.test_sem(rcgan.g_AB, dataset, dataset_location="testing/SimVerb-3500.txt",
                                        fast_text_location="fasttext_model/cc.en.300.bin")[0]
                    res.append((sl, sv))
                    print(res)
                    print("\n")
                except Exception as e:
                    print(e)
                #
                # def step_decay(initial_lrate, epoch):
                #     drop = 0.95
                #     epochs_drop = 50.0
                #     lrate = initial_lrate * math.pow(drop, math.floor((1 + epoch) / epochs_drop))  # 0.04*0.5^(1+1/10))
                #     return lrate
                # g1_current_learning_rate = step_decay(K.eval(self.g_AB.optimizer.lr),epoch)
                # g2_current_learning_rate = step_decay(K.eval(self.g_BA.optimizer.lr),epoch)
                # comb_current_learning_rate = step_decay(K.eval(self.combined.optimizer.lr),epoch)
                # d_current_learning_rate = step_decay(K.eval(self.d_A.optimizer.lr),epoch)
                # d2_current_learning_rate = step_decay(K.eval(self.d_B.optimizer.lr),epoch)
                # K.set_value(self.d_A.optimizer.lr, d_current_learning_rate)  # set new lr
                # K.set_value(self.d_B.optimizer.lr, d2_current_learning_rate)  # set new lr
                # K.set_value(self.g_AB.optimizer.lr, g1_current_learning_rate)  # set new lr
                # K.set_value(self.g_BA.optimizer.lr, g2_current_learning_rate)  # set new lr
                # K.set_value(self.combined.optimizer.lr, comb_current_learning_rate)  # set new lr

            # print("Final performance")
            # sl = tools.test_sem(rcgan.g_AB, dataset, dataset_location="testing/SimLex-999.txt",
            #                     fast_text_location="fasttext_model/cc.en.300.bin")[0]
            # sv = tools.test_sem(rcgan.g_AB, dataset, dataset_location="testing/SimVerb-3500.txt",
            #                     fast_text_location="fasttext_model/cc.en.300.bin")[0]
            # res.append((sl, sv))

        print("Actual training")
        train_(pretraining_epochs)
        print("SGD Fine tuning")
        self.compile_all("sgd")
        train_(epochs, always_random=True)
        print("Final performance")
        sl = tools.test_sem(rcgan.g_AB, dataset, dataset_location="testing/SimLex-999.txt",
                            fast_text_location="fasttext_model/cc.en.300.bin")[0]
        sv = tools.test_sem(rcgan.g_AB, dataset, dataset_location="testing/SimVerb-3500.txt",
                            fast_text_location="fasttext_model/cc.en.300.bin")[0]
        res.append((sl, sv))

        self.save_model(name="final")
        return res

    def save_model(self, name=""):
        self.d_A.save(os.path.join(self.save_folder, name + "fromretrodis.h5"), include_optimizer=False)
        self.d_B.save(os.path.join(self.save_folder, name + "toretrodis.h5"), include_optimizer=False)
        self.g_AB.save(os.path.join(self.save_folder, name + "toretrogen.h5"), include_optimizer=False)
        self.g_BA.save(os.path.join(self.save_folder, name + "fromretrogen.h5"), include_optimizer=False)
        self.combined.save(os.path.join(self.save_folder, name + "combined_model.h5"), include_optimizer=False)


if __name__ == '__main__':
    profiler.start_profiler_server(6009)
    disable_eager_execution()
    # with tf.device('/GPU:0'):
    global dimensionality
    dimensionality = 300
    tools.dimensionality = dimensionality
    postfix = "ftar"
    save_folder = "models/trained_retrogan/" + str(datetime.datetime.now()) + postfix
    if not os.path.exists(save_folder):
        os.makedirs(save_folder, exist_ok=True)
    test_ds = [
        {"original": "glove.hd5",
         "retrofitted": "glove_ar.hd5",
         "directory": "./adversarial_paper_data/",
         "rc":None},
        # {"original": "glove.hd5",
        #  "retrofitted": "glove_ar.hd5",
        #  "directory": "./adversarial_paper_data/",
        #  "rc": "adversarial_paper_data/simlexsimverb.words"},
        # {"original": "glove.hd5",
        #  "retrofitted": "glove_fdj_ar.hd5",
        #  "directory": "./adversarial_paper_data/",
        #  "rc": "./adversarial_paper_data/simlexsimverb.words"},
        {"original": "ft.hd5",
         "retrofitted": "ft_ar.hd5",
         "directory": "./adversarial_paper_data/",
         "rc":None},
        # {"original": "ft.hd5",
        #  "retrofitted": "ft_ar.hd5",
        #  "directory": "./adversarial_paper_data/",
        #  "rc": "./adversarial_paper_data/simlexsimverb.words"},
        # {"original": "ft.hd5",
        #  "retrofitted": "ft_fdj_ar.hd5",
        #  "directory": "./adversarial_paper_data/",
        #  "rc": "./adversarial_paper_data/simlexsimverb.words"}
    ]
    print("Testing")
    print(test_ds)
    print("Checking that everything exists")
    for ds in test_ds:
        a = os.path.exists(os.path.join(ds["directory"], ds["original"]))
        b = os.path.exists(os.path.join(ds["directory"], ds["retrofitted"]))
        print(a, b)
        if not a or \
                not b:
            raise FileNotFoundError("Files in " + str(ds) + "\ndo not exist")
    models = []
    results = []
    final_save_folder = "./final_retrogan"
    os.makedirs(final_save_folder, exist_ok=True)

    for idx, ds in enumerate(test_ds):
        print("Training")
        print(ds)
        rcgan = RetroCycleGAN(save_folder=save_folder, batch_size=32)
        models.append(rcgan)
        ds_res = rcgan.train(pretraining_epochs=500, epochs=0, batch_size=32, dataset=ds, rc=ds["rc"])
        results.append(ds_res)
        print("*" * 100)
        print(ds, results[-1])
        print("*" * 100)
        print("Saving")
        model_save_folder = os.path.join(final_save_folder, str(idx))
        os.makedirs(model_save_folder, exist_ok=True)
        with open(os.path.join(model_save_folder, "config"), "w") as f:
            f.write(str(ds))
        with open(os.path.join(model_save_folder, "results"), "w") as f:
            f.write(str(results[-1]))
        models[-1].save_folder = model_save_folder
        models[-1].save_model("final")
        print("Done")
