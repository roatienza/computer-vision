"""Model builder

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from tensorflow.keras.models import load_model
from tensorflow.keras.utils import plot_model
from tensorflow.keras.optimizers import Adam
from tensorflow.keras import backend as K
from tensorflow.keras.callbacks import ModelCheckpoint

import layer_utils
import label_utils
import config

import os
import skimage
import numpy as np
import argparse

from skimage.io import imread
from data_generator import DataGenerator
from model import build_basenetwork, build_ssd4
from label_utils import build_label_dictionary

class TinySSD():
    def __init__(self,
                 index=0):

        self.build_model()

    def build_model(self):

        csv_path = os.path.join(config.params['data_path'],
                                config.params['train_labels'])
        self.dictionary, self.classes  = build_label_dictionary(csv_path)
        self.n_classes = len(self.classes)
        self.keys = np.array(list(self.dictionary.keys()))

        image_path = os.path.join(config.params['data_path'],
                                  self.keys[0])
        image = skimage.img_as_float(imread(image_path))
        self.input_shape = image.shape
        base = build_basenetwork(self.input_shape)
        base.summary()

        # n_anchors = num of anchors per feature point (eg 4)
        self.n_anchors, self.feature_shape, self.ssd = build_ssd4(self.input_shape,
                                                             base,
                                                             n_classes=self.n_classes)
        self.ssd.summary()
        # print(feature_shape)
        self.train_generator = DataGenerator(dictionary=self.dictionary,
                                             n_classes=self.n_classes,
                                             params=config.params,
                                             input_shape=self.input_shape,
                                             feature_shape=self.feature_shape,
                                             index=0,
                                             n_anchors=self.n_anchors,
                                             batch_size=32,
                                             shuffle=True)


    def classes_loss(self, y_true, y_pred):
        return K.categorical_crossentropy(y_true, y_pred)


    def offsets_loss(self, y_true, y_pred):
        offset = y_true[..., 0:4]
        mask = y_true[..., 4:8]
        pred = y_pred[..., 0:4]
        offset *= mask
        pred *= mask
        return K.mean(K.square(pred - offset), axis=-1)
        

    def train_model(self):
        optimizer = Adam(lr=1e-3)
        loss = ['categorical_crossentropy', self.offsets_loss]
        self.ssd.compile(optimizer=optimizer, loss=loss)

        # prepare model model saving directory.
        save_dir = os.path.join(os.getcwd(), 'saved_models')
        model_name = 'tinyssd_weights-{epoch:03d}.h5'
        if not os.path.isdir(save_dir):
            os.makedirs(save_dir)
        filepath = os.path.join(save_dir, model_name)

        # prepare callbacks for model saving and for learning rate adjustment.
        checkpoint = ModelCheckpoint(filepath=filepath,
                                     verbose=1,
                                     save_weights_only=True,
                                     save_best_only=True)

        callbacks = [checkpoint]
        self.ssd.fit_generator(generator=self.train_generator,
                               use_multiprocessing=True,
                               callbacks=callbacks,
                               epochs=100,
                               workers=16)

    def test_generator(self):
        x, y = self.train_generator.test(0)
        print(x.shape)
        print(y[0].shape)
        print(y[1].shape)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    tinyssd = TinySSD()
    tinyssd.train_model()