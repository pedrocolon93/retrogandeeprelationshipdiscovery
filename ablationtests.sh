echo "Starting!"
CUDA_VISIBLE_DEVICES=7 python retrogan_trainer_attractrepel_working_pytorch.py --fp16 --epochs 150 ft_all_unseen.txt ft_all_unseen_retrofitted.txt retrogan_nb_full_50epochs_alllosses models/retrogan_nb_full_50epochs_alllosses &
CUDA_VISIBLE_DEVICES=1 python retrogan_trainer_attractrepel_working_pytorch.py --fp16 --epochs 150 ft_all_unseen.txt ft_all_unseen_retrofitted.txt retrogan_nb_full_50epochs_nocycledis models/retrogan_nb_full_50epochs_nocycledis --cycle_dis false &  #Original paper work
CUDA_VISIBLE_DEVICES=0 python retrogan_trainer_attractrepel_working_pytorch.py --fp16 --epochs 150 ft_all_unseen.txt ft_all_unseen_retrofitted.txt retrogan_nb_full_50epochs_nocyclemm models/retrogan_nb_full_50epochs_nocyclemmcycledis --cycle_mm false --cycle_dis false &#Original paper work
CUDA_VISIBLE_DEVICES=1 python retrogan_trainer_attractrepel_working_pytorch.py --fp16 --epochs 150 ft_all_unseen.txt ft_all_unseen_retrofitted.txt retrogan_nb_full_50epochs_nocyclemae models/retrogan_nb_full_50epochs_nocyclemaecyclemmcycledis --cycle_loss false --cycle_mm false --cycle_dis false  & #Original paper work
CUDA_VISIBLE_DEVICES=2 python retrogan_trainer_attractrepel_working_pytorch.py --fp16 --epochs 150 ft_all_unseen.txt ft_all_unseen_retrofitted.txt retrogan_nb_full_50epochs_nocycleid models/retrogan_nb_full_50epochs_nocycleididcyclemaecyclemmcycledis --cycle_loss false --cycle_mm false --cycle_dis false --id_loss false & #Original paper work
CUDA_VISIBLE_DEVICES=3 python retrogan_trainer_attractrepel_working_pytorch.py --fp16 --epochs 150 ft_all_unseen.txt ft_all_unseen_retrofitted.txt retrogan_nb_full_50epochs_noonewaymm models/retrogan_nb_full_50epochs_noonewaymmcycleididcyclemaecyclemmcycledis --cycle_loss false --cycle_mm false --cycle_dis false --id_loss false --one_way_mm false &  #Original paper work
CUDA_VISIBLE_DEVICES=6 python retrogan_trainer_attractrepel_working_pytorch.py --fp16 --epochs 150 ft_all_unseen.txt ft_all_retrofitted_ook_unseen.txt retrogan_nb_ook_50epochs_alllosses models/retrogan_nb_ook_50epochs_alllosses &
CUDA_VISIBLE_DEVICES=3 python retrogan_trainer_attractrepel_working_pytorch.py --fp16 --epochs 150 ft_all_unseen.txt ft_all_retrofitted_ook_unseen.txt retrogan_nb_ook_50epochs_nocycledis models/retrogan_nb_ook_50epochs_nocycledis --cycle_dis false &  #Original paper work
CUDA_VISIBLE_DEVICES=4 python retrogan_trainer_attractrepel_working_pytorch.py --fp16 --epochs 150 ft_all_unseen.txt ft_all_retrofitted_ook_unseen.txt retrogan_nb_ook_50epochs_nocyclemm models/retrogan_nb_ook_50epochs_nocyclemmcycledis --cycle_mm false --cycle_dis false &#Original paper work
CUDA_VISIBLE_DEVICES=5 python retrogan_trainer_attractrepel_working_pytorch.py --fp16 --epochs 150 ft_all_unseen.txt ft_all_retrofitted_ook_unseen.txt retrogan_nb_ook_50epochs_nocyclemae models/retrogan_nb_ook_50epochs_nocyclemaecyclemmcycledis --cycle_loss false --cycle_mm false --cycle_dis false  & #Original paper work
CUDA_VISIBLE_DEVICES=4 python retrogan_trainer_attractrepel_working_pytorch.py --fp16 --epochs 150 ft_all_unseen.txt ft_all_retrofitted_ook_unseen.txt retrogan_nb_ook_50epochs_nocycleid models/retrogan_nb_ook_50epochs_nocycleididcyclemaecyclemmcycledis --cycle_loss false --cycle_mm false --cycle_dis false --id_loss false & #Original paper work
CUDA_VISIBLE_DEVICES=5 python retrogan_trainer_attractrepel_working_pytorch.py --fp16 --epochs 150 ft_all_unseen.txt ft_all_retrofitted_ook_unseen.txt retrogan_nb_ook_50epochs_noonewaymm models/retrogan_nb_ook_50epochs_noonewaymmcycleididcyclemaecyclemmcycledis --cycle_loss false --cycle_mm false --cycle_dis false --id_loss false --one_way_mm false  #Original paper work
