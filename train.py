'''Trains a simple convnet on the MNIST dataset.
Gets to 99.25% test accuracy after 12 epochs
(there is still a lot of margin for parameter tuning).
16 seconds per epoch on a GRID K520 GPU.
'''

from __future__ import print_function

import argparse

import mlflow
import mlflow.keras
import mlflow.pyfunc
from mlflow.pyfunc import PythonModel
from mlflow.utils.file_utils import TempDir
from mlflow.utils.environment import _mlflow_conda_env

import cloudpickle
import tensorflow as tf

import keras
from keras.datasets import mnist
from keras.models import Sequential
from keras.layers import Dense, Dropout, Flatten
from keras.layers import Conv2D, MaxPooling2D
from keras import backend as K

parser = argparse.ArgumentParser(description='Train a Keras CNN model for MNIST classification')
parser.add_argument('--batch-size', '-b', type=int, default=128)
parser.add_argument('--epochs', '-e', type=int, default=4)
parser.add_argument('--tracking-uri', '-t',  default='http://localhost:7000')

args = parser.parse_args()

tracking_uri = args.tracking_uri
print('tracking_uri: ', tracking_uri)
batch_size = args.batch_size
epochs = args.epochs
num_classes = 10

# set up experiment
mlflow.set_tracking_uri(tracking_uri)
mlflow.set_experiment('Keras MNIST')
mlflow.start_run()

# input image dimensions
img_rows, img_cols = 28, 28

# the data, split between train and test sets
(x_train, y_train), (x_test, y_test) = mnist.load_data()

if K.image_data_format() == 'channels_first':
    x_train = x_train.reshape(x_train.shape[0], 1, img_rows, img_cols)
    x_test = x_test.reshape(x_test.shape[0], 1, img_rows, img_cols)
    input_shape = (1, img_rows, img_cols)
else:
    x_train = x_train.reshape(x_train.shape[0], img_rows, img_cols, 1)
    x_test = x_test.reshape(x_test.shape[0], img_rows, img_cols, 1)
    input_shape = (img_rows, img_cols, 1)

x_train = x_train.astype('float32')
x_test = x_test.astype('float32')
x_train /= 255
x_test /= 255
print('x_train shape:', x_train.shape)
print(x_train.shape[0], 'train samples')
print(x_test.shape[0], 'test samples')

# log the parameters
mlflow.log_param('batch_size', batch_size)
mlflow.log_param('epochs', epochs)
mlflow.log_param('training samples', x_train.shape[0])
mlflow.log_param('test samples', x_test.shape[0])

# convert class vectors to binary class matrices
y_train = keras.utils.to_categorical(y_train, num_classes)
y_test = keras.utils.to_categorical(y_test, num_classes)

model = Sequential()
model.add(Conv2D(64, (3, 3), activation='relu', input_shape=input_shape))
model.add(MaxPooling2D(pool_size=(2, 2)))
model.add(Conv2D(64, kernel_size=(3, 3), activation='relu'))
model.add(MaxPooling2D(pool_size=(2, 2)))
model.add(Dropout(0.25))
model.add(Flatten())
model.add(Dense(128, activation='relu'))
model.add(Dense(num_classes, activation='softmax'))

class LogMetricsCallback(keras.callbacks.Callback):
    def on_epoch_end(self, epoch, logs={}):
        print("logs", logs)
        mlflow.log_metric('training_loss', logs['loss'], epoch)
        mlflow.log_metric('training_accuracy', logs['acc'], epoch)
        mlflow.log_metric('validation_loss', logs['val_loss'], epoch)
        mlflow.log_metric('validation_accuracy', logs['val_acc'], epoch)

model.compile(loss=keras.losses.categorical_crossentropy,
              optimizer=keras.optimizers.Adadelta(),
              metrics=['accuracy'])

model.fit(x_train, y_train,
          batch_size=batch_size,
          epochs=epochs,
          verbose=1,
          validation_data=(x_test, y_test),
          callbacks=[LogMetricsCallback()])

# model evaluation
score = model.evaluate(x_test, y_test, verbose=0)

print('metric names', model.metrics_names)

mlflow.log_metric("test_loss", score[0])
mlflow.log_metric("test_accuracy", score[1])
print('Test loss:', score[0])
print('Test accuracy:', score[1])

#mlflow.keras.log_model(model, artifact_path="keras-model")

conda_env = _mlflow_conda_env(
    additional_conda_deps=[
        #"keras=={}".format(keras.__version__),
        #"tensorflow=={}".format(tf.__version__),
    ],
    additional_pip_deps=[
        "keras=={}".format(keras.__version__),
        "tensorflow=={}".format(tf.__version__),
        "cloudpickle=={}".format(cloudpickle.__version__),
        #"mlflow=={}".format(mlflow.__version__),
    ])

mlflow.keras.log_model(model, artifact_path="keras-model", conda_env=conda_env)

class KerasMnistCNN(PythonModel):

    def load_context(self, context):
        self.graph = tf.Graph()
        with self.graph.as_default():
            K.set_learning_phase(0)
            self.model = mlflow.keras.load_model(context.artifacts["keras-model"])

    def predict(self, context, input_df):
        with self.graph.as_default():
            return self.model.predict(input_df.values.reshape(-1, 28, 28, 1))


mlflow.pyfunc.log_model(
    artifact_path="keras-pyfunc",
    python_model=KerasMnistCNN(),
    artifacts={
        "keras-model": mlflow.get_artifact_uri("keras-model")
    },
    conda_env=conda_env)

print('experiment id:', mlflow.active_run().info.experiment_id)
print('run id:', mlflow.active_run().info.run_uuid)


mlflow.end_run()
