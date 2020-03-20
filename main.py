# coding: utf8

import numpy as np
import matplotlib.pylab as plt
import utils
import time

import pybullet as pyb
import pybullet_data
from TSID_Debug_controller_four_legs_fb_vel import controller, dt, q0, omega
import Safety_controller
import EmergencyStop_controller
import ForceMonitor
from IPython import embed
import os

########################################################################
#                        Parameters definition                         #
########################################################################

# Time step
dt_mpc = 0.02
t = 0.0  # Time

# Simulation parameters
N_SIMULATION = 1000  # number of time steps simulated

# Initialize the error for the simulation time
time_error = False

# Lists to log the duration of 1 iteration of the MPC/TSID
t_list_mpc = [0] * int(N_SIMULATION)
t_list_tsid = [0] * int(N_SIMULATION)
t_list_state = [0] * int(N_SIMULATION)

# Enable/Disable Gepetto viewer
enable_gepetto_viewer = False

# Create Joystick, ContactSequencer, FootstepPlanner, FootTrajectoryGenerator
# and MpcSolver objects
joystick, sequencer, fstep_planner, ftraj_gen, mpc, logger, mpc_interface = utils.init_objects(dt_mpc, N_SIMULATION)

########################################################################
#                            Gepetto viewer                            #
########################################################################

# Initialisation of the Gepetto viewer
solo = utils.init_viewer()

########################################################################
#                              PyBullet                                #
########################################################################

# Initialisation of the PyBullet simulator
pyb_sim = utils.pybullet_simulator(dt=0.001)

# Flag to launch the two spheres in the environment toward the robot
flag_sphere1 = True
flag_sphere2 = True

# Force monitor to display contact forces in PyBullet with red lines
myForceMonitor = ForceMonitor.ForceMonitor(pyb_sim.robotId, pyb_sim.planeId)

########################################################################
#                             Simulator                                #
########################################################################

# Define the default controller as well as emergency and safety controller
myController = controller(q0, omega, t, int(N_SIMULATION))
mySafetyController = Safety_controller.controller_12dof()
myEmergencyStop = EmergencyStop_controller.controller_12dof()

for k in range(int(N_SIMULATION)):

    # Starting time of the whole iteration
    time_start_all = time.time()

    if (k % 1000) == 0:
        print("Iteration: ", k)

    ####################################################################
    #                 Data collection from PyBullet                    #
    ####################################################################

    # Retrieve data from the simulation
    jointStates = pyb.getJointStates(pyb_sim.robotId, pyb_sim.revoluteJointIndices)  # State of all joints
    baseState = pyb.getBasePositionAndOrientation(pyb_sim.robotId)  # Position and orientation of the trunk
    baseVel = pyb.getBaseVelocity(pyb_sim.robotId)  # Velocity of the trunk

    # Joints configuration and velocity vector for free-flyer + 12 actuators
    qmes12 = np.vstack((np.array([baseState[0]]).T, np.array([baseState[1]]).T,
                        np.array([[jointStates[i_joint][0] for i_joint in range(len(jointStates))]]).T))
    vmes12 = np.vstack((np.array([baseVel[0]]).T, np.array([baseVel[1]]).T,
                        np.array([[jointStates[i_joint][1] for i_joint in range(len(jointStates))]]).T))

    # Check if the robot is in front of the first sphere to trigger it
    if flag_sphere1 and (qmes12[1, 0] >= 0.9):
        pyb.resetBaseVelocity(pyb_sim.sphereId1, linearVelocity=[3.0, 0.0, 2.0])
        flag_sphere1 = False

    # Check if the robot is in front of the second sphere to trigger it
    if flag_sphere2 and (qmes12[1, 0] >= 1.1):
        pyb.resetBaseVelocity(pyb_sim.sphereId2, linearVelocity=[-3.0, 0.0, 2.0])
        flag_sphere2 = False

    # Update the PyBullet camera on the robot position to do as if it was attached to the robot
    pyb.resetDebugVisualizerCamera(cameraDistance=0.75, cameraYaw=50, cameraPitch=-35,
                                       cameraTargetPosition=[qmes12[0, 0],qmes12[1, 0] + 0.0, 0.0])

    ########################
    # Update MPC interface #
    ########################

    t_0 = time.time()

    # Call the mpc_interface that makes the interface between the simulation and the MPC/TSID
    mpc_interface.update(solo, qmes12, vmes12)

    t_list_state[k] = time.time() - t_0

    #######################################################
    #                 Update MPC state                    #
    #######################################################

    joystick.update_v_ref(k)  # Update the reference velocity coming from the joystick
    mpc.update_v_ref(joystick)  # Retrieve reference velocity

    # Update contact sequence once every 20 iterations of TSID
    if (k > 0) and ((k % 20) == 0):
        sequencer.updateSequence()

    # Update MPC's state vectors by retrieving information from the mpc_interface
    if k > 0:
        mpc.q[0:3, 0:1] = mpc_interface.lC
        mpc.q[3:6, 0:1] = mpc_interface.abg
        mpc.v[0:3, 0:1] = mpc_interface.lV
        mpc.v[3:6, 0:1] = mpc_interface.lW

    # Run MPC once every 20 iterations of TSID
    if (k % 20) == 0:
        ###########################################
        # FOOTSTEP PLANNER & TRAJECTORY GENERATOR #
        ###########################################

        # if k > 0:  # In local frame, contacts moves in the opposite direction of the base
        # ftraj_gen.update_frame(mpc.v)  # Update contacts depending on the velocity of the base

        # Update desired location of footsteps using the footsteps planner
        fstep_planner.update_footsteps_mpc(sequencer, mpc, mpc_interface)

        # Update 3D desired feet pos using the trajectory generator
        # ftraj_gen.update_desired_feet_pos(sequencer, fstep_planner, mpc)

        ###################
        #  MPC FUNCTIONS  #
        ###################

        time_mpc = time.time()

        # Run the MPC to get the reference forces and the next predicted state
        # Result is stored in mpc.f_applied, mpc.q_next, mpc.v_next
        mpc.run((k/20), sequencer, fstep_planner, ftraj_gen, mpc_interface)

        # Time spent to run this iteration of the MPC
        time_spent = time.time() - time_mpc

        # Logging the time spent
        t_list_mpc[k] = time_spent

        # Visualisation with gepetto viewer
        if enable_gepetto_viewer:
            utils.display_all(solo, k, sequencer, fstep_planner, ftraj_gen, mpc)

        # Logging various stuff
        # logger.call_log_functions(sequencer, fstep_planner, ftraj_gen, mpc, k)

        f_applied = mpc.f_applied

    if False:  # k in [228]:
        fc = mpc.x[mpc.xref.shape[0] * (mpc.xref.shape[1]-1):].reshape((12, -1), order='F')

        # Plot desired contact forces
        plt.figure()
        c = ["r", "g", "b", "rebeccapurple"]
        legends = ["FL", "FR", "HL", "HR"]
        for i in range(4):
            plt.subplot(3, 4, i+1)
            plt.plot(fc[3*i, :], color="r", linewidth=3)
            plt.xlabel("Time [s]")
            plt.ylabel("Contact force along X [N]")
            plt.legend([legends[i] + "_MPC"])

        for i in range(4):
            plt.subplot(3, 4, i+5)
            plt.plot(fc[3*i+1, :], color="r", linewidth=3)
            plt.xlabel("Time [s]")
            plt.ylabel("Contact force along Y [N]")
            plt.legend([legends[i] + "_MPC"])

        for i in range(4):
            plt.subplot(3, 4, i+9)
            plt.plot(fc[3*i+2, :], color="r", linewidth=3)
            plt.xlabel("Time [s]")
            plt.ylabel("Contact force along Z [N]")
            plt.legend([legends[i] + "_MPC"])

        # Evolution of the position and orientation of the robot over time
        plt.figure()
        ylabels = ["Position X", "Position Y", "Position Z",
                   "Orientation Roll", "Orientation Pitch", "Orientation Yaw"]
        for i, j in enumerate([1, 3, 5, 2, 4, 6]):
            plt.subplot(3, 2, j)
            plt.plot(mpc.x_robot[i, :], "b", linewidth=2)
            plt.legend(["Robot"])
            plt.xlabel("Time [s]")
            plt.ylabel(ylabels[i])

        # Evolution of the linear and angular velocities of the robot over time
        plt.figure()
        ylabels = ["Linear vel X", "Linear vel Y", "Linear vel Z",
                   "Angular vel Roll", "Angular vel Pitch", "Angular vel Yaw"]
        for i, j in enumerate([1, 3, 5, 2, 4, 6]):
            plt.subplot(3, 2, j)
            plt.plot(mpc.x_robot[i+6, :], "b", linewidth=2)
            plt.legend(["Robot"])
            plt.xlabel("Time [s]")
            plt.ylabel(ylabels[i])

        plt.show(block=False)

        embed()

    ##############
    # TSID BLOCK #
    ##############

    for i in range(1):

        time_start = time.time()

        ####################################################################
        #                Select the appropriate controller 				   #
        #                               &								   #
        #               Load the joint torques into the robot			   #
        ####################################################################

        # If the limit bounds are reached, controller is switched to a pure derivative controller
        """if(myController.error):
            print("Safety bounds reached. Switch to a safety controller")
            myController = mySafetyController"""

        # If the simulation time is too long, controller is switched to a zero torques controller
        """time_error = time_error or (time.time()-time_start > 0.01)
        if (time_error):
            print("Computation time lasted to long. Switch to a zero torque control")
            myController = myEmergencyStop"""

        # Retrieve the joint torques from the appropriate controller
        jointTorques = myController.control(qmes12, vmes12, t, i+k, solo,
                                            sequencer, mpc_interface, joystick.v_ref, f_applied).reshape((12, 1))

        # Time incrementation
        t += dt

        # Time spent to run this iteration of the loop
        time_spent = time.time() - time_start

        # Logging the time spent
        t_list_tsid[k] = time_spent

        ############
        # PYBULLET #
        ############

        # Set control torque for all joints
        pyb.setJointMotorControlArray(pyb_sim.robotId, pyb_sim.revoluteJointIndices,
                                      controlMode=pyb.TORQUE_CONTROL, forces=jointTorques)

        # Apply perturbation
        """if k >= 50 and k < 100:
            pyb.applyExternalForce(pyb_sim.robotId, -1, [1.0, 0.0, 0.0], [0.0, 0.0, 0.0], pyb.LINK_FRAME)
        if k >= 150 and k < 200:
            pyb.applyExternalForce(pyb_sim.robotId, -1, [0.0, 1.0, 0.0], [0.0, 0.0, 0.0], pyb.LINK_FRAME)"""

        # Compute one step of simulation
        pyb.stepSimulation()

        # Refresh force monitoring for PyBullet
        # myForceMonitor.display_contact_forces()

        # Save PyBullet camera frame
        """img = pyb.getCameraImage(width=1920, height=1080, renderer=pyb.ER_BULLET_HARDWARE_OPENGL)
        if k == 0:
            newpath = r'/tmp/recording'
            if not os.path.exists(newpath):
                os.makedirs(newpath)
        plt.imsave('/tmp/recording/frame_'+str(k)+'.png', img[2])"""

####################
# END OF MAIN LOOP #
####################

print(np.mean(t_list_state))

plt.figure()
plt.plot(t_list_mpc, 'k+')
plt.title("Time MPC")

plt.figure()
plt.plot(t_list_tsid, 'k+')
plt.title("Time TSID")
plt.show(block=True)

quit()

# Display graphs of the logger
logger.plot_graphs(dt_mpc, N_SIMULATION, myController)

# Plot TSID related graphs
plt.figure()
for i in range(4):
    plt.subplot(2, 2, 1*i+1)
    plt.title("Trajectory of the front right foot over time")
    l_str = ["X", "Y", "Z"]
    plt.plot(myController.f_pos_ref[i, :, 2], linewidth=2, marker='x')
    plt.plot(myController.f_pos[i, :, 2], linewidth=2, marker='x')
    plt.plot(myController.h_ref_feet, linewidth=2, marker='x')
    plt.legend(["FR Foot ref pos along " + l_str[2], "FR foot pos along " + l_str[2], "Zero altitude"])
    plt.xlim((0, 70))

plt.figure()
plt.title("Trajectory of the front right foot over time")
l_str = ["X", "Y", "Z"]
for i in range(3):
    plt.subplot(3, 1, 1*i+1)
    plt.plot(myController.f_pos_ref[1, :, i])
    plt.plot(myController.f_pos[1, :, i])
    if i == 2:
        plt.plot(myController.h_ref_feet)
        plt.legend(["FR Foot ref pos along " + l_str[i], "FR foot pos along " + l_str[i], "Zero altitude"])
    else:
        plt.legend(["FR Foot ref pos along " + l_str[i], "FR foot pos along " + l_str[i]])
    plt.xlim((20, 40))
plt.figure()
plt.title("Velocity of the front right foot over time")
l_str = ["X", "Y", "Z"]
for i in range(3):
    plt.subplot(3, 1, 1*i+1)
    plt.plot(myController.f_vel_ref[1, :, i])
    plt.plot(myController.f_vel[1, :, i])
    plt.legend(["FR Foot ref vel along " + l_str[i], "FR foot vel along " + l_str[i]])
    plt.xlim((20, 40))
    """plt.subplot(3, 3, 3*i+3)
    plt.plot(myController.f_acc_ref[1, :, i])
    plt.plot(myController.f_acc[1, :, i])
    plt.legend(["Ref acc along " + l_str[i], "Acc along " + l_str[i]])"""

plt.figure()
l_str = ["X", "Y", "Z", "Roll", "Pitch", "Yaw"]
for i in range(3):
    plt.subplot(3, 1, i+1)
    plt.plot(myController.b_pos[:, i])
    if i < 2:
        plt.plot(np.zeros((N_SIMULATION,)))
    else:
        plt.plot((0.2027682) * np.ones((N_SIMULATION,)))
    plt.legend([l_str[i] + "of base", l_str[i] + "reference of base"])

plt.figure()
l_str = ["X", "Y", "Z", "Roll", "Pitch", "Yaw"]
for i in range(3):
    plt.subplot(3, 1, i+1)
    plt.plot(myController.b_vel[:, i])
    plt.plot(np.zeros((N_SIMULATION,)))
    plt.legend(["Velocity of base along" + l_str[i], "Reference velocity of base along" + l_str[i]])

if hasattr(myController, 'com_pos_ref'):
    plt.figure()
    plt.title("Trajectory of the CoM over time")
    for i in range(3):
        plt.subplot(3, 1, i+1)
        plt.plot(myController.com_pos_ref[:, i], "b", linewidth=3)
        plt.plot(myController.com_pos[:, i], "r", linewidth=2)
        plt.legend(["CoM ref pos along " + l_str[0], "CoM pos along " + l_str[0]])


plt.show()

plt.figure(9)
plt.plot(t_list_tsid, 'k+')
plt.show()

quit()
