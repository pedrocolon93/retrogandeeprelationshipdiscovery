import datetime

import os
import pickle

import numpy as np
from keras import Model, Input
from keras.layers import Dense, BatchNormalization, Concatenate, Dropout, LeakyReLU
from keras.optimizers import RMSprop

from tools import load_training_input_2
from vaetest1 import VAE, sampling


class RetroCycleGAN():
    def __init__(self, input_vae, output_vae):
        self.in_vae = input_vae
        self.out_vae = output_vae
        # Input shape
        self.img_rows = 1
        self.img_cols = 300
        self.channels = 1
        self.img_shape = (self.img_cols,)#, self.channels)

        # Configure data loader
        self.dataset_name = 'apple2orange'
        # self.data_loader = DataLoader(dataset_name=self.dataset_name,
        #                               img_res=(self.img_rows, self.img_cols))


        # Calculate output shape of D (PatchGAN)
        # patch = int(self.img_rows / 2**4)
        # self.disc_patch = (patch, patch, 1)

        # Number of filters in the first layer of G and D
        self.gf = 64
        self.df = 256

        # Loss weights
        self.lambda_cycle = 10.0                    # Cycle-consistency loss
        self.lambda_id = 0.1 * self.lambda_cycle    # Identity loss

        # optimizer = Adam(0.0002, 0.5,amsgrad=True)
        # optimizer = Adam()
        # optimizer = Nadam()
        # optimizer = SGD(lr=0.01,nesterov=True,momentum=0.8,decay=0.1e-8)
        # optimizer = Adadelta()
        optimizer = RMSprop(lr=0.005)
        # Build and compile the discriminators
        self.d_A = self.build_discriminator()
        self.d_B = self.build_discriminator()
        self.d_A.compile(loss='mse',
            optimizer=optimizer,
            metrics=['accuracy'])
        self.d_B.compile(loss='mse',
            optimizer=optimizer,
            metrics=['accuracy'])

        #-------------------------
        # Construct Computational
        #   Graph of Generators
        #-------------------------

        # Build the generators
        self.g_AB = self.build_generator()
        self.g_AB.summary()
        self.g_BA = self.build_generator()
        self.g_BA.summary()
        # Input images from both domains
        img_A = Input(shape=self.img_shape)
        img_B = Input(shape=self.img_shape)

        # Translate images to the other domain
        fake_B = self.g_AB(img_A)
        fake_A = self.g_BA(img_B)
        # Translate images back to original domain
        reconstr_A = self.g_BA(fake_B)
        reconstr_B = self.g_AB(fake_A)
        # Identity mapping of images
        img_A_id = self.g_BA(img_A)
        img_B_id = self.g_AB(img_B)

        # For the combined model we will only train the generators
        self.d_A.trainable = False
        self.d_B.trainable = False

        # Discriminators determines validity of translated images
        valid_A = self.d_A(fake_A)
        valid_B = self.d_B(fake_B)

        # Combined model trains generators to fool discriminators
        self.combined = Model(inputs=[img_A, img_B],
                              outputs=[ valid_A, valid_B,
                                        reconstr_A, reconstr_B,
                                        img_A_id, img_B_id ])
        self.combined.compile(loss=['mse', 'mse',
                                    'mae', 'mae',
                                    'mae', 'mae'],
                            loss_weights=[  1, 1,
                                            self.lambda_cycle, self.lambda_cycle,
                                            self.lambda_id, self.lambda_id ],
                            optimizer=optimizer)

    def build_generator(self):
        """U-Net Generator"""

        def dense(layer_input, layer_size):
            """Layers used during downsampling"""
            # d = Conv2D(filters, kernel_size=f_size, strides=2, padding='same')(layer_input)
            # d = LeakyReLU(alpha=0.2)(d)
            # d = InstanceNormalization()(d)
            d = Dense(layer_size)(layer_input)
            d = LeakyReLU(alpha=0.2)(d)
            d = BatchNormalization()(d)
            return d

        def undense(layer_input, skip_input, layer_size,  dropout_rate=0):
            """Layers used during upsampling"""
            # u = UpSampling2D(size=2)(layer_input)
            # u = Conv2D(filters, kernel_size=f_size, strides=1, padding='same', activation='relu')(u)
            u = Dense(layer_size,activation='relu')(layer_input)
            if dropout_rate:
                u = Dropout(dropout_rate)(u)
            u = BatchNormalization()(u)
            # u = InstanceNormalization()(u)
            u = Concatenate()([u, skip_input])
            return u

        # Image input
        d0 = Input(shape=self.img_shape)

        # Downsampling
        d1 = dense(d0, self.gf)
        d2 = dense(d1, self.gf*2)
        d3 = dense(d2, self.gf*4)
        d4 = dense(d3, self.gf*8)

        # Upsampling
        u1 = undense(d4, d3, self.gf*4)
        u2 = undense(u1, d2, self.gf*2)
        u3 = undense(u2, d1, self.gf)

        # u4 = UpSampling2D(size=2)(u3)
        # u4 = Dense(2048)
        # output_img = Conv2D(self.channels, kernel_size=4, strides=1, padding='same', activation='tanh')(u4)
        output_img = Dense(self.img_cols,activation='tanh')(u3)
        return Model(d0, output_img)

    def build_discriminator(self):

        def d_layer(layer_input, layer_size,  normalization=True):
            """Discriminator layer"""
            d = Dense(layer_size, activation='relu')(layer_input)
            # d = LeakyReLU(alpha=0.2)(d)
            if normalization:
                d = BatchNormalization()(d)
            return d

        img = Input(shape=self.img_shape)

        d1 = d_layer(img, self.df, normalization=False)
        d2 = d_layer(d1, self.df*2)
        d3 = d_layer(d2, self.df*4)
        d4 = d_layer(d3, self.df*8)

        validity = Dense(1,activation='sigmoid')(d4)

        return Model(img, validity)

    def train(self, epochs, batch_size=1, sample_interval=50,noisy_entries_num=5):

        start_time = datetime.datetime.now()

        # Adversarial loss ground truths
        valid = np.ones((batch_size*noisy_entries_num,) )
        fake = np.zeros((batch_size*noisy_entries_num,) )
        # X_train, Y_train, X_test, Y_test = (None,None,None,None)
        # if os.path.exists("training_testing.data"):
        #     print("Loading data")
        #     data = pickle.load(open('training_testing.data','rb'))
        #     X_train = data["X_train"]
        #     Y_train = data["Y_train"]
        #     X_test = data["X_test"]
        #     Y_test = data["Y_test"]
        # else:
            # print("Dumping data")
        X_train = Y_train = X_test = Y_test = None
        file = "data.pickle"
        if not os.path.exists(file):
            X_train, Y_train, X_test, Y_test = load_training_input_2()
            pickle.dump((X_train, Y_train, X_test, Y_test), open(file, "wb"))
        else:
            X_train, Y_train, X_test, Y_test = pickle.load(open("data.pickle", 'rb'))
            # data = {
            #     'X_train':X_train,
            #            'Y_train':Y_train, 'X_test':X_test, 'Y_test':Y_test
            # }
            # pickle.dump(data,open('training_testing.data','wb'))
        n_batches = 900
        def load_batch(batch_size,train_test = True,n_batches = 900):
            for i in range(n_batches):
                if train_test:
                    idx = np.random.randint(0, X_train.shape[0], batch_size)
                    imgs_A = X_train[idx]
                    imgs_B = Y_train[idx]
                    yield imgs_A, imgs_B
                else:
                    idx = np.random.randint(0, X_test.shape[0], batch_size)
                    imgs_A = X_test[idx]
                    imgs_B = Y_test[idx]
                    yield imgs_A, imgs_B
        for epoch in range(epochs):


            for batch_i, (imgs_A, imgs_B) in enumerate(load_batch(batch_size)):

                # ----------------------
                #  Train Discriminators
                # ----------------------

                # self.latent_dim = 300
                # # idx = np.random.randint(0, X_train.shape[0], batch_size)
                # noisy_entries = []
                # noisy_outputs = []
                # for index in range(len(imgs_A)):
                #     # Generate some noise
                #     input_noise = output_noise = noise = np.random.normal(0, 0.1, (noisy_entries_num, self.latent_dim))
                #     # Replace one for the original
                #     input_noise[0, :] = imgs_A[index]
                #     output_noise[0, :] = imgs_B[index]
                #     # Add noise to the original to have some noisy inputs
                #     for i in range(1, noise.shape[0]):
                #         input_noise[i, :] = imgs_A[index] + noise[i, :]
                #         output_noise[i, :] = imgs_B[index] + noise[i, :]
                #
                #     noisy_entries.append(input_noise)
                #     noisy_outputs.append(output_noise)
                # # imgs = Y_train[idx]
                # imgs = noisy_outputs[0]
                # noise = noisy_entries[0]
                # # print("imgs")
                # # print(imgs.shape)
                # # print("noise")
                # # print(noise.shape)
                # for entry_idx in range(1, len(noisy_outputs)):
                #     # print(noisy_outputs[entry_idx].shape)
                #     imgs = np.vstack((imgs, noisy_outputs[entry_idx]))
                #     noise = np.vstack((noise, noisy_entries[entry_idx]))
                noisy_entries = []
                noisy_outputs = []
                for index in range(batch_size):
                    #sample for input
                    dist = self.in_vae.predict(imgs_A[index,:])
                    samples = []
                    for i in range(noisy_entries_num):
                        samples.append(sampling(dist))
                    noisy_entries.append(samples)
                    #sample for output
                    dist = self.out_vae.predict(imgs_B[index,:])
                    samples = []
                    for i in range(noisy_entries_num):
                        samples.append(sampling(dist))
                    noisy_outputs.append(samples)
                #join
                noise = noisy_entries[0,:]
                imgs = noisy_outputs[0,:]

                for entry_idx in range(1, len(noisy_outputs)):
                    # print(noisy_outputs[entry_idx].shape)
                    imgs = np.vstack((imgs, noisy_outputs[entry_idx]))
                    noise = np.vstack((noise, noisy_entries[entry_idx]))


                imgs_A = noise
                imgs_B = imgs


                # Translate images to opposite domain
                fake_B = self.g_AB.predict(imgs_A)
                fake_A = self.g_BA.predict(imgs_B)

                # Train the discriminators (original images = real / translated = Fake)
                dA_loss_real = self.d_A.train_on_batch(imgs_A, valid)
                dA_loss_fake = self.d_A.train_on_batch(fake_A, fake)
                dA_loss = 0.5 * np.add(dA_loss_real, dA_loss_fake)

                dB_loss_real = self.d_B.train_on_batch(imgs_B, valid)
                dB_loss_fake = self.d_B.train_on_batch(fake_B, fake)
                dB_loss = 0.5 * np.add(dB_loss_real, dB_loss_fake)

                # Total disciminator loss
                d_loss = 0.5 * np.add(dA_loss, dB_loss)

                # ------------------
                #  Train Generators
                # ------------------

                # Train the generators
                g_loss = self.combined.train_on_batch([imgs_A, imgs_B],
                                                        [valid, valid,
                                                        imgs_A, imgs_B,
                                                        imgs_A, imgs_B])

                elapsed_time = datetime.datetime.now() - start_time

                # Plot the progress
                print ("[Epoch %d/%d] [Batch %d/%d] [D loss: %f, acc: %3d%%] [G loss: %05f, adv: %05f, recon: %05f, id: %05f] time: %s " \
                                                                        % ( epoch, epochs,
                                                                            batch_i, n_batches,
                                                                            d_loss[0], 100*d_loss[1],
                                                                            g_loss[0],
                                                                            np.mean(g_loss[1:3]),
                                                                            np.mean(g_loss[3:5]),
                                                                            np.mean(g_loss[5:6]),
                                                                            elapsed_time))


        self.X_test = X_test
        self.Y_test = Y_test
        pickle.dump(self, open('model.pickle', 'wb'))


if __name__ == '__main__':
    X_train= Y_train= X_test= Y_test = None
    file = "data.pickle"
    if not os.path.exists(file):
        X_train, Y_train, X_test, Y_test = load_training_input_2()
        pickle.dump((X_train, Y_train, X_test, Y_test), open(file, "wb"))
    else:
        X_train, Y_train, X_test, Y_test = pickle.load(open("data.pickle",'rb'))


    print("Min\tMax")
    print("Train")
    print(np.min(X_train),np.max(X_train))
    print(np.min(Y_train),np.max(Y_train))
    print("Test")
    print(np.min(X_test),np.max(X_test))
    print(np.min(Y_test),np.max(Y_test))
    print("End")

    #
    input_vae = VAE()
    input_vae.create_vae()
    input_vae.configure_vae()
    input_vae.compile_vae()
    input_vae.fit(X_train,X_test,"input_vae.h5")
    print(X_test)
    print(input_vae.predict(X_test))


    output_vae = VAE()
    output_vae.create_vae()
    output_vae.configure_vae()
    output_vae.compile_vae()
    output_vae.fit(Y_train, Y_test,"output_vae.h5")
    print(Y_test)
    print(input_vae.predict(Y_test))

    rcgan = RetroCycleGAN(input_vae,output_vae)


