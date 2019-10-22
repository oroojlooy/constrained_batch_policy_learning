
import numpy as np
import keras
from keras.models import Sequential, Model as KerasModel
from keras.layers import Input, Dense, Flatten, concatenate, dot
from keras.losses import mean_squared_error
from keras import optimizers
from keras.callbacks import Callback, TensorBoard
from exact_policy_evaluation import ExactPolicyEvaluator
from keras_tqdm import TQDMCallback
from model import Model

from keras.layers.convolutional import Conv2D


class NN(Model):
    def __init__(self, num_inputs, num_outputs, grid_shape, dim_of_actions, gamma, convergence_of_model_epsilon=1e-10, model_type='mlp', position_of_holes=None, position_of_goals=None):
        '''
        An implementation of fitted Q iteration

        num_inputs: number of inputs
        num_outputs: number of outputs
        dim_of_actions: dimension of action space
        convergence_of_model_epsilon: small float. Defines when the model has converged.
        '''
        super(NN, self).__init__()
        self.convergence_of_model_epsilon = convergence_of_model_epsilon 
        self.model_type = model_type
        self.dim_of_actions = dim_of_actions
        self.dim_of_state = grid_shape[0] * grid_shape[1]
        self.grid_shape = grid_shape

        if self.model_type == 'cnn':
            assert position_of_holes is not None
            assert position_of_goals is not None

        
        self.position_of_goals = position_of_goals

        if position_of_holes is not None:
            self.position_of_holes = np.zeros(self.dim_of_state)
            self.position_of_holes[position_of_holes] = 1
            self.position_of_holes = self.position_of_holes.reshape(self.grid_shape)
        else:
            self.position_of_holes = position_of_holes

        if position_of_goals is not None:
            self.position_of_goals = np.zeros(self.dim_of_state)
            self.position_of_goals[position_of_goals] = 1
            self.position_of_goals = self.position_of_goals.reshape(self.grid_shape)
        else:
            self.position_of_goals = position_of_goals

        self.model = self.create_model(num_inputs, num_outputs)
        #debug purposes
        self.policy_evalutor = ExactPolicyEvaluator([0], num_inputs-dim_of_actions, gamma)

    def copy_over_to(self, to_):
        to_.model.set_weights(self.model.get_weights())

    def create_model(self, num_inputs, num_outputs):
        if self.model_type == 'mlp':
            model = Sequential()
            def init(): return keras.initializers.TruncatedNormal(mean=0.0, stddev=0.001, seed=np.random.randint(2**32))
            model.add(Dense(64, activation='tanh', input_shape=(num_inputs,),kernel_initializer=init(), bias_initializer=init()))
            model.add(Dense(num_outputs, activation='linear',kernel_initializer=init(), bias_initializer=init()))
            # adam = optimizers.Adam(clipnorm=1.)
            model.compile(loss='mean_squared_error', optimizer='Adam', metrics=['accuracy'])
        elif self.model_type == 'cnn':
            # input layer
            # 3 channels: holes, goals, player
            # and actions
            def init(): seed=np.random.randint(2**32); return keras.initializers.TruncatedNormal(mean=0.0, stddev=0.001, seed=seed)
            inp = Input(shape=(self.grid_shape[0],self.grid_shape[1],1), name='grid')
            actions = Input(shape=(self.dim_of_actions,), name='mask')
            neighbors = Input(shape=(2*self.dim_of_actions,), name='holes_and_goals')
            
            # Grid feature extraction

            seed = np.random.randint(2**32)

            conv1 = Conv2D(16, kernel_size=2, activation='elu', padding='SAME', data_format='channels_last',kernel_initializer=init(), bias_initializer=init())(inp)
            # conv2 = Conv2D(16, kernel_size=3, activation='elu', padding='SAME', data_format='channels_last',kernel_initializer=init(), bias_initializer=init())(conv1)
            flat1 = Flatten()(conv1)
            
            # Holes + goals feature extractor
            # flat2 = Dense(20, activation='elu',kernel_initializer=init(), bias_initializer=init())(neighbors)
            
            # merge feature extractors
            # merge = concatenate([flat1, flat2])
            
            # interpret
            hidden1 = Dense(10, activation='elu',kernel_initializer=init(), bias_initializer=init())(flat1)
            hidden2 = Dense(self.dim_of_actions, activation='linear',kernel_initializer=init(), bias_initializer=init())(hidden1)
            
            output = dot([hidden2, actions], 1)
            # predict
            # output = Dense(1, activation='linear',kernel_initializer=init(), bias_initializer=init())(hidden1)
            model = KerasModel(inputs=[inp, neighbors, actions], outputs=output)
            model.compile(loss='mean_squared_error', optimizer='Adam', metrics=['accuracy'])
        else:
            raise NotImplemented

        # model.summary()
        return model


    def fit(self, X, y, verbose=0, batch_size=512, epochs=1000, evaluate=False, tqdm_verbose=True, **kw):

        X = self.representation(X[:,0], X[:, 1])
        self.callbacks_list = [EarlyStoppingByConvergence(epsilon=self.convergence_of_model_epsilon, diff =1e-10, verbose=verbose)]#, TQDMCallback(show_inner=False, show_outer=tqdm_verbose)]
        self.model.fit(X,y,verbose=verbose==2, batch_size=batch_size, epochs=epochs, callbacks=self.callbacks_list, **kw)

        if evaluate:
            return self.evaluate()
        else:
            return None

    def representation(self, *args):
        if self.model_type == 'mlp':
            if len(args) == 1:
                return np.eye(self.dim_of_state)[np.array(args[0]).astype(int)]
            elif len(args) == 2:
                return np.hstack([np.eye(self.dim_of_state)[np.array(args[0]).astype(int)], np.eye(self.dim_of_actions)[np.array(args[1]).astype(int)] ])
            else:
                raise NotImplemented
        elif self.model_type == 'cnn':
            if len(args) == 1:
                position = np.eye(self.dim_of_state)[np.array(args[0]).astype(int)].reshape(-1,self.grid_shape[0],self.grid_shape[1])
                X, surrounding = self.create_cnn_rep_helper(position)
                return [X, surrounding]
            elif len(args) == 2:
                position = np.eye(self.dim_of_state)[np.array(args[0]).astype(int)].reshape(-1,self.grid_shape[0],self.grid_shape[1])
                X, surrounding = self.create_cnn_rep_helper(position)
                return [X, surrounding, np.eye(self.dim_of_actions)[np.array(args[1]).astype(int)] ]
            else:
                raise NotImplemented
        else:
            raise NotImplemented

    def create_cnn_rep_helper(self, position):
        how_many = position.shape[0]
        holes = np.repeat(self.position_of_holes[np.newaxis, :, :], how_many, axis=0)
        goals = np.repeat(self.position_of_goals[np.newaxis, :, :], how_many, axis=0)

        ix_x, ix_y, ix_z = np.where(position)
        surrounding = self.is_next_to([self.position_of_holes, self.position_of_goals], ix_y, ix_z)

        return np.sum([position*.5, holes*1, goals*(-1)], axis = 0)[:,:,:,np.newaxis], np.hstack(surrounding)

    def is_next_to(self, obstacles, x, y):
        # obstacles must be list
        assert np.all(np.array([obstacle.shape for obstacle in obstacles]) == obstacles[0].shape)
        surround = lambda x,y: [(x, y-1), (x+1, y), (x, y+1), (x-1, y)]

        ret = []
        for idx in range(len(x)):
            neighbors = []
            for a,b in surround(x[idx], y[idx]):
                # only works if all obstacles are same shape
                neighbor = np.vstack([obstacle[a, b] for obstacle in obstacles]) if 0 <= a < obstacles[0].shape[0] and 0 <= b < obstacles[0].shape[1] else np.array([0.]*len(obstacles)).reshape(1,-1).T
                neighbors.append(neighbor)

            ret.append(np.hstack(neighbors))

        return np.stack(ret, axis=1)

    def predict(self, X, a):
        return self.model.predict(self.representation(X,a))

    def all_actions(self, X):
        # X_a = ((x_1, a_1)
               # (x_1, a_2)
               #  ....
               # (x_1, a_m)
               # ...
               # (x_N, a_1)
               # (x_N, a_2)
               #  ...
               #  ...
               # (x_N, a_m))
        X = np.array(X)
        X_a = self.cartesian_product(X, np.arange(self.dim_of_actions))


        # Q_x_a = ((Q_x1_a1, Q_x1_a2,... Q_x1_am)
                 # (Q_x2_a1, Q_x2_a2,... Q_x2_am)
                 # ...
                 # (Q_xN_a1, Q_xN_a2,... Q_xN_am)
        # by reshaping using C ordering

        Q_x_a = self.predict(X_a[:,0], X_a[:,1]).reshape(X.shape[0],self.dim_of_actions,order='C')
        return Q_x_a

class EarlyStoppingByConvergence(Callback):
    def __init__(self, monitor='loss', epsilon=0.01, diff=.001, use_both=True, verbose=0):
        super(Callback, self).__init__()
        self.monitor = monitor
        self.epsilon = epsilon
        self.diff = diff
        self.use_both = use_both
        self.verbose = verbose
        self.losses_so_far = []
        self.converged = False

    def on_epoch_end(self, epoch, logs={}):
        self.epoch = epoch
        
        current = logs.get(self.monitor)
        if current is None:
            print("Early stopping requires %s available!" % self.monitor)
            exit()
        else:
            self.losses_so_far.append(current)

        if self.verbose:
            if (self.epoch % 100) == 0:
                print('Epoch %s, loss: %s' % (epoch, self.losses_so_far[-1]))
        
        if self.use_both:
            if ((len(self.losses_so_far) > 1) and (np.abs(self.losses_so_far[-2] - self.losses_so_far[-1]) < self.epsilon)) or (self.losses_so_far[-1] < self.diff):
                self.model.stop_training = True
                self.converged = True
            else:
                pass
        else:
            if ((len(self.losses_so_far) > 1) and (np.abs(self.losses_so_far[-2] - self.losses_so_far[-1]) < self.epsilon)):
                self.model.stop_training = True
                self.converged = True
            else:
                pass


    def on_train_end(self, logs=None):
        if self.epoch > 1:
            if self.verbose > 0:
                if self.converged:
                    print('Epoch %s: early stopping. Converged. Delta: %s. Loss: %s' % (self.epoch, np.abs(self.losses_so_far[-2] - self.losses_so_far[-1]), self.losses_so_far[-1]))
                else:
                    print('Epoch %s. NOT converged. Delta: %s. Loss: %s' % (self.epoch, np.abs(self.losses_so_far[-2] - self.losses_so_far[-1]), self.losses_so_far[-1]))

    def on_train_begin(self, logs=None):
        # Allow instances to be re-used
        self.losses_so_far = []
        self.converged = False


            
        
