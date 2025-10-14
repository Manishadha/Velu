#!/usr/bin/env bash
set -euo pipefail

source ~/.bashrc
velu_stop
velu_server

# submit plan and process exactly plan+code+tests
velu_pipeline hello_mod "smoke"
velu_worker_once 3

# print the test result
velu_wait_test "$TEST_JOB"
