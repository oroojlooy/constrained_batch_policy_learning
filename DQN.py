import keras
import numpy as np
from replay_buffer import Buffer
import time


class DeepQLearning(object):
    def __init__(self, env, 
                       gamma, 
                       model_type='mlp', 
                       action_space_map = None,
                       num_iterations = 5000, 
                       sample_every_N_transitions = 10,
                       batchsize = 1000,
                       copy_over_target_every_M_training_iterations = 100,
                       max_time_spent_in_episode = 100,
                       buffer_size = 10000,
                       num_frame_stack=1,
                       min_buffer_size_to_train=1000,
                       frame_skip = 1,
                       pic_size = (96, 96),
                       ):
        self.env = env
        self.num_iterations = num_iterations
        self.gamma = gamma
        self.frame_skip = frame_skip
        self.buffer = Buffer(buffer_size=buffer_size, num_frame_stack=num_frame_stack, min_buffer_size_to_train=min_buffer_size_to_train, pic_size = pic_size)
        self.sample_every_N_transitions = sample_every_N_transitions
        self.batchsize = batchsize
        self.copy_over_target_every_M_training_iterations = copy_over_target_every_M_training_iterations
        self.max_time_spent_in_episode = max_time_spent_in_episode
        self.action_space_map = action_space_map

    def min_over_a(self, *args, **kw):
        return self.Q.min_over_a(*args, **kw)

    def all_actions(self, *args, **kw):
        return self.Q.all_actions(*args, **kw)

    def learn(self):
        

        self.time_steps = 0
        training_iteration = -1
        perf = Performance()
        main_tic = time.time()
        for i in range(self.num_iterations):
            tic = time.time()
            x = self.env.reset()
            self.buffer.start_new_episode(x)
            done = False
            time_spent_in_episode = 0
            episode_cost = 0
            while not done:
                self.env.render()
                time_spent_in_episode += 1
                self.time_steps += 1
                # print time_spent_in_episode
                
                action = self.Q(self.buffer.current_state())[0]
                use_random = np.random.rand(1) < self.epsilon(i)
                if use_random:
                    action = self.sample_random_action()

                if (i % 50) == 0: print use_random, action, self.Q(self.buffer.current_state())[0], self.Q.all_actions(self.buffer.current_state())

                # import pdb; pdb.set_trace()
                # state = self.buffer.current_state()
                # import matplotlib.pyplot as plt
                # plt.imshow(state[-1])
                # plt.show()
                # self.Q.all_actions(state)

                cost = 0
                for _ in range(self.frame_skip):
                    if done: continue
                    x_prime, costs, done, _ = self.env.step(self.action_space_map[action])
                    cost += costs[0]
                    
                early_done, punishment = self.env.is_early_episode_termination(cost=cost)
          
                cost += punishment
                done = done or early_done
                

                # self.buffer.append([x,action,x_prime, cost[0], done])
                
                self.buffer.append(action, x_prime, cost, done)

                # train
                is_train = ((self.time_steps % self.sample_every_N_transitions) == 0) and self.buffer.is_enough()

                if is_train:
                    # for _ in range(len(self.buffer.data)/self.sample_every_N_transitions):
                    training_iteration += 1
                    if (training_iteration % self.copy_over_target_every_M_training_iterations) == 0: 
                        self.Q.copy_over_to(self.Q_target)
                    batch_x, batch_a, batch_x_prime, batch_cost, batch_done = self.buffer.sample(self.batchsize)

                    target = batch_cost + self.gamma*self.Q_target.min_over_a(np.stack(batch_x_prime))[0]*(1-batch_done)
                    X = [batch_x, batch_a]
                    
                    evaluation = self.Q.fit(X,target,epochs=1, batch_size=self.batchsize,evaluate=False,verbose=False,tqdm_verbose=False)
                
                x = x_prime

                episode_cost += cost

            perf.append(episode_cost/self.env.min_cost)

            if (i % 1) == 0:
                print 'Episode %s' % i
                episode_time = time.time()-tic
                print 'Total Time: %s. Episode time: %s. Time/Frame: %s' % (np.round(time.time() - main_tic,2), np.round(episode_time, 2), np.round(episode_time/time_spent_in_episode, 2))
                print 'Episode frames: %s. Total frames: %s. Total train steps: %s' % (time_spent_in_episode, self.time_steps, training_iteration)
                print 'Performance: %s. Average performance: %s' %  (perf.last(), perf.get_avg_performance())
                print '*'*20
            if perf.reached_goal():
                return

    def __call__(self,*args):
        return self.Q.__call__(*args)

class Performance(object):
    def __init__(self):
        self.goal = .85
        self.avg_over = 100
        self.costs = []

    def reached_goal(self):
        if self.get_avg_performance() >= self.goal:
            return True
        else:
            return False

    def append(self, cost):
        self.costs.append(cost)

    def last(self):
        return np.round(self.costs[-1], 3)

    def get_avg_performance(self):
        num_iters = min(self.avg_over, len(self.costs))
        return np.round(sum(self.costs[-num_iters:])/ float(num_iters), 3)

# class Buffer(object):
#     def __init__(self, buffer_size=10000):
#         self.data = []
#         self.size = buffer_size
#         self.idx = -1

#     def append(self, datum):
#         self.idx = (self.idx + 1) % self.size
        
#         if len(self.data) > self.idx:
#             self.data[self.idx] = datum
#         else:
#             self.data.append(datum)

#     def sample(self, N):
#         N = min(N, len(self.data))
#         rows = np.random.choice(len(self.data), size=N, replace=False)
#         return np.array(self.data)[rows]



