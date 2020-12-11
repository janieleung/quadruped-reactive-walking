#ifndef QPWBC_H_INCLUDED
#define QPWBC_H_INCLUDED

#include <iostream>
#include <fstream>
#include <string>
#include <cmath>
#include <limits>
#include <vector>
#include <Eigen/Core>
#include <Eigen/Dense>
#include "osqp_folder/include/osqp.h"
#include "osqp_folder/include/cs.h"
#include "osqp_folder/include/auxil.h"
#include "osqp_folder/include/util.h"
#include "osqp_folder/include/osqp_configure.h"
#include "other/st_to_cc.hpp"

class QPWBC {
 private:
  
  int cpt_ML = 0;
  int cpt_P = 0;

  // Set to True after the creation of the QP problem during the first call of the solver
  bool initialized = false;

  // Weight matrices of initial QP
  Eigen::Matrix<double, 6, 6> Q1 = 0.1 * Eigen::Matrix<double, 6, 6>::Identity();
  Eigen::Matrix<double, 12, 12> Q2 = 1.0 * Eigen::Matrix<double, 12, 12>::Identity();

  // Friction coefficient
  const double mu = 0.9;

  // Generatrix of the linearized friction cone
  Eigen::Matrix<double, 12, 16> G = 1.0 * Eigen::Matrix<double, 12, 16>::Zero();

  // Results
  Eigen::Matrix<double, 16, 1> lambdas = Eigen::Matrix<double, 16, 1>::Zero();
  Eigen::MatrixXd f_res = Eigen::MatrixXd::Zero(12, 1);
  Eigen::MatrixXd ddq_res = Eigen::MatrixXd::Zero(12, 1);
  
  // Matrix ML
  const static int size_nz_ML = 16;
  csc *ML;  // Compressed Sparse Column matrix

  // Matrix NK
  const static int size_nz_NK = 16;
  double v_NK_up[size_nz_NK] = {};   // matrix NK (upper bound)
  double v_NK_low[size_nz_NK] = {};  // matrix NK (lower bound)
  double v_warmxf[size_nz_NK] = {};  // matrix NK (lower bound)

  // Matrix P
  const static int size_nz_P = 256;
  csc *P;  // Compressed Sparse Column matrix

  // Matrix Q
  const static int size_nz_Q = 16;
  double Q[size_nz_Q] = {};  // Q is full of zeros

  // OSQP solver variables
  OSQPWorkspace *workspce = new OSQPWorkspace();
  OSQPData *data;
  OSQPSettings *settings = (OSQPSettings *)c_malloc(sizeof(OSQPSettings));

 public:
  
  QPWBC(); // Constructor

  // Functions
  inline void add_to_ML(int i, int j, double v, int *r_ML, int *c_ML, double *v_ML); // function to fill the triplet r/c/v
  inline void add_to_P(int i, int j, double v, int *r_P, int *c_P, double *v_P); // function to fill the triplet r/c/v
  int create_matrices();
  int create_ML();
  int create_weight_matrices();
  int compute_matrices(const Eigen::MatrixXd &M, const Eigen::MatrixXd &Jc, const Eigen::MatrixXd &f_cmd, const Eigen::MatrixXd &RNEA);
  void update_PQ();
  int call_solver(int);
  int retrieve_result();
  int run(const Eigen::MatrixXd &M, const Eigen::MatrixXd &Jc, const Eigen::MatrixXd &f_cmd, const Eigen::MatrixXd &RNEA);

  // Getters
  Eigen::MatrixXd QPWBC::get_f_res();
  Eigen::MatrixXd QPWBC::get_dsqq_res();

  // Utils
  void my_print_csc_matrix(csc *M, const char *name);
  void save_csc_matrix(csc *M, std::string filename);
  void save_dns_matrix(double *M, int size, std::string filename);

};

#endif  // QPWBC_H_INCLUDED