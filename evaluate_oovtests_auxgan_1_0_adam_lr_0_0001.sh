# Directory: /home/yxin/research/projects/RetroGAN-DRD/retrogandeeprelationshipdiscovery

source evaluate_oovtests_auxgan.sh

OOVTEST_DIR=oovtest-1_0-adam-lr-0_0001
CUDA_VISIBLE_DEVICES=2

evaluate_simlex && evaluate_simverb
