from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import sys
import time
import pprint
from random import shuffle
import numpy as np
import tensorflow as tf

import common
import files
import image
import image_dataset as img_ds
from image import LabeledImage
from image_dataset import ImageDataset


def build_app_flags():
    # Global app parameters
    # They are accessible everywhere in the application via tf.app.flags.FLAGS

    # General flags
    tf.app.flags.DEFINE_string("model_dir", "../models/stl10/adamOp_1_eps0.1_lr_0.0005",
                               "Model checkpoint/training/evaluation data directory")
    tf.app.flags.DEFINE_float("dropout_rate", 0.3, "Dropout rate for model training")
    tf.app.flags.DEFINE_integer("eval_batch_size", 64, "Evaluation data batch size")
    tf.app.flags.DEFINE_integer("train_batch_size", 64, "Training data batch size")

    # Learning rate flags
    tf.app.flags.DEFINE_float("initial_learning_rate", 0.0005,
                              "Initial value for learning rate")
    tf.app.flags.DEFINE_bool("use_static_learning_rate", True,
                             "Flag that determines if learning rate should be constant value")
    tf.app.flags.DEFINE_float("learning_rate_decay_rate", 0.96, "Learning rate decay rate")
    tf.app.flags.DEFINE_integer("learning_rate_decay_steps", 2000, "Learning rate decay steps")

    # GPU flags
    tf.app.flags.DEFINE_bool("ignore_gpu", False,
                             "Flag that determines if gpu should be disabled")
    tf.app.flags.DEFINE_float("per_process_gpu_memory_fraction", 1.0,
                              "Fraction of gpu memory to be used")

    # Image flags
    tf.app.flags.DEFINE_integer("image_width", 96, "Image width")
    tf.app.flags.DEFINE_integer("image_height", 96, "Image height")
    tf.app.flags.DEFINE_integer("image_channels", 3, "Image channels")


def get_model_params():
    return {"add_layer_summaries": True}


def load_train_dataset():
    dataset = ImageDataset.load_from_pickles([
        "/datasets/stl10/original_train.pkl",
        "/datasets/stl10/mirror_train.pkl",
        # "/datasets/stl10/rand_distorted_train.pkl",
        "/datasets/stl10/rand_distorted_train_0.pkl",
        "/datasets/stl10/rand_distorted_train_1.pkl",
        "/datasets/stl10/rand_distorted_train_2.pkl",
    ])

    return dataset.x, dataset.y


def load_eval_dataset():
    dataset = ImageDataset.load_from_pickles([
        "/datasets/stl10/original_test.pkl",
    ])

    return dataset.x, dataset.y


def load_original(images_dtype=np.float32, labels_dtype=np.int32):
    files.maybe_download_and_extract(
        dest_dir="../data",
        data_url="http://ai.stanford.edu/~acoates/stl10/stl10_binary.tar.gz",
        nested_dir="stl10_binary"
    )

    # data paths
    train_x_path = '../data/stl10_binary/train_X.bin'
    train_y_path = '../data/stl10_binary/train_y.bin'

    test_x_path = '../data/stl10_binary/test_X.bin'
    test_y_path = '../data/stl10_binary/test_y.bin'

    def read_labels(path_to_labels):
        with open(path_to_labels, 'rb') as f:
            return np.fromfile(f, dtype=np.uint8)

    def read_images(path_to_data):
        with open(path_to_data, 'rb') as f:
            everything = np.fromfile(f, dtype=np.uint8)
            images = np.reshape(everything, (-1, 3, 96, 96))

            return np.transpose(images, (0, 3, 2, 1))

    # load images/labels from binary file
    train_x = read_images(train_x_path)
    train_y = read_labels(train_y_path)

    test_x = read_images(test_x_path)
    test_y = read_labels(test_y_path)

    # prepare images/labels for training
    train_x = common.prepare_images(train_x, dtype=images_dtype)
    train_y = np.asarray(train_y, dtype=labels_dtype)

    test_x = common.prepare_images(test_x, dtype=images_dtype)
    test_y = np.asarray(test_y, dtype=labels_dtype)

    return (train_x, np.add(train_y, -1)), (test_x, np.add(test_y, -1))


def get_class_names():
    with open("../data/stl10_binary/class_names.txt") as f:
        content = f.readlines()

    class_names = [x.strip() for x in content]

    return class_names


def model_fn(features, labels, mode, params, config):

    app_flags = tf.app.flags.FLAGS

    # Input Layer
    with tf.name_scope("input_layer"):
        # if mode == tf.estimator.ModeKeys.TRAIN:
        #     input_layer = tf.map_fn(
        #         fn=lambda img: image.randomly_distort_image(
        #             image=img,
        #             crop_shape=(72, 72, 3),
        #             target_size=96,
        #         ),
        #         elems=features["x"],
        #         parallel_iterations=128
        #     )
        # else:
        input_layer = features["x"]

    # Convolution 1
    conv1 = tf.layers.conv2d(
        inputs=input_layer,
        filters=96,
        kernel_size=[7, 7],
        strides=2,
        padding="same",
        activation=tf.nn.relu,
        name="conv1"
    )

    pool1 = tf.layers.max_pooling2d(
        inputs=conv1,
        pool_size=[3, 3],
        strides=2,
        padding="same",
        name="pool1"
    )

    # Convolution 2
    conv2 = tf.layers.conv2d(
        inputs=pool1,
        filters=128,
        kernel_size=[5, 5],
        strides=1,
        padding="same",
        activation=tf.nn.relu,
        name="conv2"
    )
    pool2 = tf.layers.max_pooling2d(
        inputs=conv2,
        pool_size=[2, 2],
        strides=2,
        name="pool2"
    )

    # Convolution 3
    conv3 = tf.layers.conv2d(
        inputs=pool2,
        filters=172,
        kernel_size=[3, 3],
        strides=1,
        padding="same",
        activation=tf.nn.relu,
        name="conv3"
    )
    pool3 = tf.layers.max_pooling2d(
        inputs=conv3,
        pool_size=[2, 2],
        strides=2,
        name="pool3"
    )

    # Convolution 4
    conv4 = tf.layers.conv2d(
        inputs=pool3,
        filters=256,
        kernel_size=[3, 3],
        strides=1,
        padding="same",
        activation=tf.nn.relu,
        name="conv4"
    )

    # Flatten output of the last convolution
    pool_flat = tf.reshape(
        conv4, [-1, conv4.shape[1]*conv4.shape[2]*conv4.shape[3]], name="pool_flat")

    # Dense Layers
    dense1 = tf.layers.dense(
        inputs=pool_flat,
        units=1024,
        activation=tf.nn.relu,
        name="dense1"
    )

    dense2 = tf.layers.dense(
        inputs=dense1,
        units=512,
        activation=tf.nn.relu,
        name="dense2"
    )

    dense3 = tf.layers.dense(
        inputs=dense2,
        units=256,
        activation=tf.nn.relu,
        name="dense3"
    )

    if params.get("add_layer_summaries", False) is True:
        weighted_layers_names = ["conv1", "conv2", "conv3", "conv4", "dense1", "dense2", "dense3"]
        for layer_name in weighted_layers_names:
            common.build_layer_summaries(layer_name)

    with tf.name_scope("dropout"):
        dropout = tf.layers.dropout(
            inputs=dense3, rate=app_flags.dropout_rate, training=mode == tf.estimator.ModeKeys.TRAIN)

    # Logits Layer
    logits = tf.layers.dense(inputs=dropout, units=10, name="logits")

    argmax = tf.argmax(input=logits, axis=1, name="predictions", output_type=tf.int32)

    top_k_values, top_k_indices = tf.nn.top_k(input=logits, k=2)
    tf.identity(top_k_values, "top_k_values")
    tf.identity(top_k_indices, "top_k_indices")

    softmax = tf.nn.softmax(logits, name="softmax_tensor")

    predictions = {
        "class": argmax,
        "logits": logits,
        "probabilities": softmax
    }

    if mode == tf.estimator.ModeKeys.PREDICT:
        return tf.estimator.EstimatorSpec(mode=mode, predictions=predictions)

    # Add name to labels tensor
    labels = tf.identity(labels, name="labels")

    # Calculate Loss
    loss = tf.losses.sparse_softmax_cross_entropy(labels=labels, logits=logits, scope="calc_loss")
    tf.summary.scalar("cross_entropy", loss)

    # Configure the TrainingOp
    if mode == tf.estimator.ModeKeys.TRAIN:

        summary_saver_hook = tf.train.SummarySaverHook(
            save_steps=100,
            output_dir=config.model_dir + "/train",
            summary_op=tf.summary.merge_all()
        )

        # Gradient Descent Optimizer configuration with learning rate decay
        # learning_rate = common.get_learning_rate_from_flags(tf.app.flags.FLAGS)
        # optimizer = tf.train.GradientDescentOptimizer(
        #     learning_rate=learning_rate, name="gradient_descent_optimizer")

        optimizer = tf.train.AdamOptimizer(
            learning_rate=tf.app.flags.FLAGS.initial_learning_rate,
            epsilon=0.01,
            name="adam_optimizer"
        )
        train_op = optimizer.minimize(
            loss=loss, global_step=tf.train.get_global_step(), name="minimize_loss")

        return tf.estimator.EstimatorSpec(
            mode=mode,
            loss=loss,
            train_op=train_op,
            training_hooks=[summary_saver_hook]
        )

    # Add evaluation metrics
    eval_metric_ops = {
        "accuracy": tf.metrics.accuracy(labels=labels, predictions=predictions["class"])
    }

    return tf.estimator.EstimatorSpec(
        mode=mode,
        loss=loss,
        eval_metric_ops=eval_metric_ops,
    )


if __name__ == "__main__":
    train, test = load_original()

    train, test = img_ds.split_dataset(
        images=np.concatenate([train[0], test[0]], axis=0),
        labels=np.concatenate([train[1], test[1]], axis=0),
        test_items_fraction=0.25,
    )

    print(test[0].shape, test[0].dtype, test[1].shape, test[1].dtype)
    print(train[0].shape, train[0].dtype, train[1].shape, train[1].dtype)

    img_ds.improve_dataset(
        train,
        test,
        "stl10",
        crop_shape=(72, 72, 3),
        target_size=96,
        rand_dist_sets=0,
        save_location="../datasets"
    )