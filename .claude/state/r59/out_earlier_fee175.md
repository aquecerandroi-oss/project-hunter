## cobertura
modo=earlier min_cover=1s taxa=1.75% por perna
| set | apostas | elegiveis | sem serie | cobertura mediana (s) | hold mediano (s) |
|---|---|---|---|---|---|
| operator/5 real | 12 | 12 | 0 | 92 | 102 |
| operator/5 | 19 | 19 | 0 | 51 | 73 |
| flow_v2/5 | 139 | 137 | 1 | 62 | 76 |
| flow_v2/2 | 165 | 163 | 1 | 62 | 76 |
| flow_v2/6 | 25 | 25 | 0 | 67 | 79 |
| flow_v2/8 | 31 | 31 | 0 | 62 | 76 |

## operator/5 real
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 12 | 8% | -0.124 | -0.0741 | 0.0741 | — | creator_dump=7, time_stop=3, trailing=2 |
| a2_actual_exit_mcap_fee1.25 | 12 | 8% | -0.107 | -0.0640 | 0.0640 | — | creator_dump=7, time_stop=3, trailing=2 |
| b_line_broken(2) | 12 | 17% | -0.080 | -0.0480 | 0.0527 | — | actual:creator_dump=5, actual:time_stop=1, actual:trailing=1, line_broken=5 |
| b2_paper_full_set | 12 | 17% | -0.107 | -0.0642 | 0.0642 | — | actual:creator_dump=3, actual:time_stop=1, actual:trailing=1, creator_dump=2, line_broken=5 |
| c_trail15 | 12 | 17% | -0.087 | -0.0520 | 0.0544 | — | actual:creator_dump=6, actual:time_stop=1, actual:trailing=1, trailing=4 |
| c_trail30 | 12 | 8% | -0.106 | -0.0637 | 0.0637 | — | actual:creator_dump=6, actual:time_stop=2, actual:trailing=1, trailing=3 |
| c_trail50 | 12 | 8% | -0.107 | -0.0640 | 0.0640 | — | actual:creator_dump=7, actual:time_stop=3, actual:trailing=2 |
| d_arm+25%_trail30 | 12 | 8% | -0.106 | -0.0638 | 0.0638 | — | actual:creator_dump=6, actual:time_stop=3, actual:trailing=1, trailing=2 |
| d_arm+50%_trail30 | 12 | 8% | -0.107 | -0.0640 | 0.0640 | — | actual:creator_dump=7, actual:time_stop=3, actual:trailing=2 |
| d_arm+100%_trail30 | 12 | 8% | -0.107 | -0.0640 | 0.0640 | — | actual:creator_dump=7, actual:time_stop=3, actual:trailing=2 |
| d_arm+25%_trail15 | 12 | 25% | -0.081 | -0.0483 | 0.0566 | — | actual:creator_dump=6, actual:time_stop=3, actual:trailing=1, trailing=2 |
| d_arm+50%_trail15 | 12 | 8% | -0.107 | -0.0640 | 0.0640 | — | actual:creator_dump=7, actual:time_stop=3, actual:trailing=2 |
| d_tp+25%_else_trail30 | 12 | 25% | -0.073 | -0.0435 | 0.0614 | — | actual:creator_dump=5, actual:time_stop=2, actual:trailing=1, target=3, trailing=1 |
| d_tp+50%_else_trail30 | 12 | 8% | -0.101 | -0.0608 | 0.0608 | — | actual:creator_dump=5, actual:time_stop=2, actual:trailing=1, target=1, trailing=3 |
| d_tp+100%_else_trail30 | 12 | 8% | -0.106 | -0.0637 | 0.0637 | — | actual:creator_dump=6, actual:time_stop=2, actual:trailing=1, trailing=3 |
| e_time2m | 12 | 17% | -0.080 | -0.0477 | 0.0558 | — | actual:creator_dump=6, actual:trailing=1, time_stop=5 |
| e_time5m | 12 | 25% | -0.038 | -0.0230 | 0.0493 | — | actual:creator_dump=6, actual:trailing=1, time_stop=5 |
| e_time15m | 12 | 8% | -0.103 | -0.0619 | 0.0619 | — | actual:creator_dump=7, actual:trailing=2, time_stop=3 |
| e_time30m | 12 | 8% | -0.107 | -0.0640 | 0.0640 | — | actual:creator_dump=7, actual:time_stop=3, actual:trailing=2 |
| f_first_creator_sell | 12 | 8% | -0.134 | -0.0801 | 0.0801 | — | actual:creator_dump=3, actual:time_stop=3, actual:trailing=2, creator_sell=4 |
| f2_creator_sell_incl_15s_net_seller | 12 | 8% | -0.130 | -0.0777 | 0.0777 | — | actual:creator_dump=2, actual:time_stop=3, actual:trailing=2, creator_sell=5 |
| g_tp30_or_trail20_or_5m | 12 | 17% | -0.100 | -0.0599 | 0.0599 | — | actual:creator_dump=5, actual:trailing=1, target=2, time_stop=2, trailing=2 |
| g2_tp30_or_trail20_or_2m | 12 | 17% | -0.111 | -0.0663 | 0.0663 | — | actual:creator_dump=5, actual:trailing=1, target=2, time_stop=2, trailing=2 |
| g3_tp50_or_trail20_or_5m | 12 | 17% | -0.074 | -0.0444 | 0.0493 | — | actual:creator_dump=5, actual:trailing=1, target=1, time_stop=3, trailing=2 |
| g4_tp30_or_trail15_or_5m | 12 | 17% | -0.101 | -0.0604 | 0.0604 | — | actual:creator_dump=5, actual:trailing=1, target=2, time_stop=1, trailing=3 |
| g5_tp30_or_trail15_or_2m | 12 | 17% | -0.101 | -0.0603 | 0.0603 | — | actual:creator_dump=5, actual:trailing=1, target=2, time_stop=1, trailing=3 |
| h_tp100_or_trail30_or_5m | 12 | 25% | -0.038 | -0.0230 | 0.0493 | — | actual:creator_dump=6, actual:trailing=1, time_stop=5 |
| h2_tp100_or_trail30_or_15m | 12 | 8% | -0.103 | -0.0617 | 0.0617 | — | actual:creator_dump=6, actual:trailing=1, time_stop=3, trailing=2 |
| h3_tp100_or_trail30_or_30m | 12 | 8% | -0.106 | -0.0637 | 0.0637 | — | actual:creator_dump=6, actual:time_stop=2, actual:trailing=1, trailing=3 |
| h4_tp300_or_trail30_or_30m | 12 | 8% | -0.106 | -0.0637 | 0.0637 | — | actual:creator_dump=6, actual:time_stop=2, actual:trailing=1, trailing=3 |

## operator/5
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 19 | 26% | -0.025 | -0.0240 | 0.0729 | — | creator_dump=9, line_broken=9, time_stop=1 |
| a2_actual_exit_mcap_fee1.25 | 19 | 26% | -0.023 | -0.0218 | 0.0710 | — | creator_dump=9, line_broken=9, time_stop=1 |
| b_line_broken(2) | 19 | 26% | +0.004 | +0.0042 | 0.0451 | 2591% | actual:creator_dump=9, actual:line_broken=4, actual:time_stop=1, line_broken=5 |
| b2_paper_full_set | 19 | 26% | +0.012 | +0.0117 | 0.0422 | 946% | actual:creator_dump=5, actual:line_broken=4, actual:time_stop=1, creator_dump=4, line_broken=5 |
| c_trail15 | 19 | 21% | -0.068 | -0.0644 | 0.0777 | — | actual:creator_dump=9, actual:line_broken=4, trailing=6 |
| c_trail30 | 19 | 26% | -0.023 | -0.0217 | 0.0709 | — | actual:creator_dump=9, actual:line_broken=9, trailing=1 |
| c_trail50 | 19 | 26% | -0.023 | -0.0218 | 0.0710 | — | actual:creator_dump=9, actual:line_broken=9, actual:time_stop=1 |
| d_arm+25%_trail30 | 19 | 26% | -0.023 | -0.0218 | 0.0710 | — | actual:creator_dump=9, actual:line_broken=9, actual:time_stop=1 |
| d_arm+50%_trail30 | 19 | 26% | -0.023 | -0.0218 | 0.0710 | — | actual:creator_dump=9, actual:line_broken=9, actual:time_stop=1 |
| d_arm+100%_trail30 | 19 | 26% | -0.023 | -0.0218 | 0.0710 | — | actual:creator_dump=9, actual:line_broken=9, actual:time_stop=1 |
| d_arm+25%_trail15 | 19 | 26% | -0.061 | -0.0578 | 0.0710 | — | actual:creator_dump=9, actual:line_broken=8, actual:time_stop=1, trailing=1 |
| d_arm+50%_trail15 | 19 | 26% | -0.061 | -0.0578 | 0.0710 | — | actual:creator_dump=9, actual:line_broken=8, actual:time_stop=1, trailing=1 |
| d_tp+25%_else_trail30 | 19 | 26% | -0.064 | -0.0604 | 0.0729 | — | actual:creator_dump=8, actual:line_broken=6, target=4, trailing=1 |
| d_tp+50%_else_trail30 | 19 | 26% | -0.026 | -0.0244 | 0.0551 | — | actual:creator_dump=9, actual:line_broken=7, target=2, trailing=1 |
| d_tp+100%_else_trail30 | 19 | 26% | +0.012 | +0.0113 | 0.0449 | 1021% | actual:creator_dump=9, actual:line_broken=8, target=1, trailing=1 |
| e_time2m | 19 | 26% | -0.061 | -0.0583 | 0.0745 | — | actual:creator_dump=8, actual:line_broken=5, time_stop=6 |
| e_time5m | 19 | 26% | +0.024 | +0.0230 | 0.0432 | 544% | actual:creator_dump=9, actual:line_broken=8, time_stop=2 |
| e_time15m | 19 | 26% | -0.021 | -0.0200 | 0.0692 | — | actual:creator_dump=9, actual:line_broken=9, time_stop=1 |
| e_time30m | 19 | 26% | -0.023 | -0.0218 | 0.0710 | — | actual:creator_dump=9, actual:line_broken=9, actual:time_stop=1 |
| f_first_creator_sell | 19 | 26% | -0.015 | -0.0143 | 0.0675 | — | actual:creator_dump=5, actual:line_broken=9, actual:time_stop=1, creator_sell=4 |
| f2_creator_sell_incl_15s_net_seller | 19 | 26% | -0.013 | -0.0123 | 0.0655 | — | actual:creator_dump=4, actual:line_broken=9, actual:time_stop=1, creator_sell=5 |
| g_tp30_or_trail20_or_5m | 19 | 26% | -0.050 | -0.0476 | 0.0601 | — | actual:creator_dump=8, actual:line_broken=4, target=4, trailing=3 |
| g2_tp30_or_trail20_or_2m | 19 | 26% | -0.064 | -0.0612 | 0.0737 | — | actual:creator_dump=7, actual:line_broken=3, target=3, time_stop=3, trailing=3 |
| g3_tp50_or_trail20_or_5m | 19 | 26% | -0.024 | -0.0232 | 0.0539 | — | actual:creator_dump=9, actual:line_broken=5, target=2, trailing=3 |
| g4_tp30_or_trail15_or_5m | 19 | 21% | -0.063 | -0.0603 | 0.0728 | — | actual:creator_dump=8, actual:line_broken=3, target=3, trailing=5 |
| g5_tp30_or_trail15_or_2m | 19 | 21% | -0.063 | -0.0597 | 0.0722 | — | actual:creator_dump=7, actual:line_broken=2, target=3, time_stop=2, trailing=5 |
| h_tp100_or_trail30_or_5m | 19 | 26% | +0.014 | +0.0130 | 0.0432 | 888% | actual:creator_dump=9, actual:line_broken=8, target=1, time_stop=1 |
| h2_tp100_or_trail30_or_15m | 19 | 26% | +0.014 | +0.0130 | 0.0432 | 888% | actual:creator_dump=9, actual:line_broken=8, target=1, time_stop=1 |
| h3_tp100_or_trail30_or_30m | 19 | 26% | +0.012 | +0.0113 | 0.0449 | 1021% | actual:creator_dump=9, actual:line_broken=8, target=1, trailing=1 |
| h4_tp300_or_trail30_or_30m | 19 | 26% | -0.023 | -0.0217 | 0.0709 | — | actual:creator_dump=9, actual:line_broken=9, trailing=1 |

## flow_v2/5
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 137 | 39% | -0.001 | -0.0082 | 0.2652 | — | creator_dump=41, line_broken=77, max_loss=12, migrated=2, target=1, time_stop=2, trailing=2 |
| a2_actual_exit_mcap_fee1.25 | 137 | 39% | +0.001 | +0.0035 | 0.2638 | 6683% | creator_dump=41, line_broken=77, max_loss=12, migrated=2, target=1, time_stop=2, trailing=2 |
| b_line_broken(2) | 137 | 38% | -0.013 | -0.0891 | 0.2598 | — | actual:creator_dump=41, actual:line_broken=51, actual:max_loss=12, actual:migrated=1, actual:target=1, actual:time_stop=2, actual:trailing=2, line_broken=27 |
| b2_paper_full_set | 137 | 37% | -0.017 | -0.1145 | 0.2501 | — | actual:creator_dump=29, actual:line_broken=51, actual:max_loss=5, actual:migrated=1, actual:time_stop=2, actual:trailing=2, creator_dump=12, line_broken=27, max_loss=7, target=1 |
| c_trail15 | 137 | 37% | +0.001 | +0.0081 | 0.1830 | 2655% | actual:creator_dump=29, actual:line_broken=54, actual:max_loss=1, actual:migrated=2, actual:target=1, actual:trailing=1, trailing=49 |
| c_trail30 | 137 | 40% | +0.011 | +0.0766 | 0.2415 | 305% | actual:creator_dump=38, actual:line_broken=74, actual:max_loss=1, actual:migrated=2, actual:target=1, actual:time_stop=1, actual:trailing=2, trailing=18 |
| c_trail50 | 137 | 39% | +0.003 | +0.0196 | 0.2524 | 1192% | actual:creator_dump=41, actual:line_broken=77, actual:max_loss=4, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, trailing=8 |
| d_arm+25%_trail30 | 137 | 40% | +0.005 | +0.0370 | 0.2638 | 631% | actual:creator_dump=41, actual:line_broken=77, actual:max_loss=10, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, trailing=2 |
| d_arm+50%_trail30 | 137 | 40% | +0.005 | +0.0355 | 0.2638 | 657% | actual:creator_dump=41, actual:line_broken=77, actual:max_loss=11, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, trailing=1 |
| d_arm+100%_trail30 | 137 | 39% | +0.001 | +0.0035 | 0.2638 | 6683% | actual:creator_dump=41, actual:line_broken=77, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2 |
| d_arm+25%_trail15 | 137 | 41% | -0.010 | -0.0694 | 0.2242 | — | actual:creator_dump=39, actual:line_broken=71, actual:max_loss=10, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=1, trailing=11 |
| d_arm+50%_trail15 | 137 | 40% | -0.012 | -0.0832 | 0.2389 | — | actual:creator_dump=40, actual:line_broken=73, actual:max_loss=11, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=1, trailing=7 |
| d_tp+25%_else_trail30 | 137 | 45% | -0.020 | -0.1347 | 0.1955 | — | actual:creator_dump=26, actual:line_broken=56, actual:time_stop=1, target=38, trailing=16 |
| d_tp+50%_else_trail30 | 137 | 42% | -0.004 | -0.0242 | 0.1969 | — | actual:creator_dump=33, actual:line_broken=63, actual:time_stop=1, target=23, trailing=17 |
| d_tp+100%_else_trail30 | 137 | 41% | +0.027 | +0.1875 | 0.2001 | 115% | actual:creator_dump=38, actual:line_broken=71, actual:migrated=1, actual:time_stop=1, actual:trailing=1, target=7, trailing=18 |
| e_time2m | 137 | 39% | -0.022 | -0.1524 | 0.2515 | — | actual:creator_dump=33, actual:line_broken=59, actual:max_loss=11, actual:migrated=2, actual:trailing=2, time_stop=30 |
| e_time5m | 137 | 39% | -0.004 | -0.0269 | 0.2632 | — | actual:creator_dump=40, actual:line_broken=70, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:trailing=2, time_stop=10 |
| e_time15m | 137 | 39% | +0.001 | +0.0050 | 0.2638 | 4647% | actual:creator_dump=41, actual:line_broken=77, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:trailing=2, time_stop=2 |
| e_time30m | 137 | 39% | +0.001 | +0.0035 | 0.2638 | 6683% | actual:creator_dump=41, actual:line_broken=77, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2 |
| f_first_creator_sell | 137 | 39% | -0.007 | -0.0499 | 0.2703 | — | actual:creator_dump=29, actual:line_broken=77, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, creator_sell=12 |
| f2_creator_sell_incl_15s_net_seller | 137 | 39% | -0.013 | -0.0879 | 0.2526 | — | actual:creator_dump=17, actual:line_broken=75, actual:max_loss=10, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, creator_sell=28 |
| g_tp30_or_trail20_or_5m | 137 | 42% | -0.017 | -0.1154 | 0.2227 | — | actual:creator_dump=22, actual:line_broken=50, target=32, time_stop=4, trailing=29 |
| g2_tp30_or_trail20_or_2m | 137 | 41% | -0.020 | -0.1370 | 0.2132 | — | actual:creator_dump=21, actual:line_broken=48, target=29, time_stop=11, trailing=28 |
| g3_tp50_or_trail20_or_5m | 137 | 39% | -0.006 | -0.0437 | 0.2004 | — | actual:creator_dump=28, actual:line_broken=52, target=21, time_stop=5, trailing=31 |
| g4_tp30_or_trail15_or_5m | 137 | 40% | -0.013 | -0.0887 | 0.2110 | — | actual:creator_dump=20, actual:line_broken=45, target=31, time_stop=3, trailing=38 |
| g5_tp30_or_trail15_or_2m | 137 | 39% | -0.014 | -0.0961 | 0.2016 | — | actual:creator_dump=19, actual:line_broken=43, target=29, time_stop=10, trailing=36 |
| h_tp100_or_trail30_or_5m | 137 | 41% | +0.020 | +0.1396 | 0.2001 | 154% | actual:creator_dump=37, actual:line_broken=68, actual:migrated=1, actual:trailing=1, target=5, time_stop=8, trailing=17 |
| h2_tp100_or_trail30_or_15m | 137 | 41% | +0.027 | +0.1875 | 0.2001 | 115% | actual:creator_dump=38, actual:line_broken=71, actual:migrated=1, actual:trailing=1, target=7, time_stop=1, trailing=18 |
| h3_tp100_or_trail30_or_30m | 137 | 41% | +0.027 | +0.1875 | 0.2001 | 115% | actual:creator_dump=38, actual:line_broken=71, actual:migrated=1, actual:time_stop=1, actual:trailing=1, target=7, trailing=18 |
| h4_tp300_or_trail30_or_30m | 137 | 40% | +0.013 | +0.0884 | 0.2415 | 277% | actual:creator_dump=38, actual:line_broken=74, actual:max_loss=1, actual:migrated=2, actual:time_stop=1, actual:trailing=2, target=1, trailing=18 |

## flow_v2/2
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 163 | 40% | +0.009 | +0.0750 | 0.2703 | 378% | creator_dump=53, line_broken=89, max_loss=14, migrated=2, target=1, time_stop=2, trailing=2 |
| a2_actual_exit_mcap_fee1.25 | 163 | 40% | +0.011 | +0.0896 | 0.2683 | 318% | creator_dump=53, line_broken=89, max_loss=14, migrated=2, target=1, time_stop=2, trailing=2 |
| b_line_broken(2) | 163 | 39% | -0.000 | -0.0003 | 0.2605 | — | actual:creator_dump=53, actual:line_broken=55, actual:max_loss=14, actual:migrated=1, actual:target=1, actual:time_stop=2, actual:trailing=2, line_broken=35 |
| b2_paper_full_set | 163 | 38% | -0.004 | -0.0308 | 0.2556 | — | actual:creator_dump=39, actual:line_broken=55, actual:max_loss=6, actual:migrated=1, actual:time_stop=2, actual:trailing=2, creator_dump=14, line_broken=35, max_loss=8, target=1 |
| c_trail15 | 163 | 39% | +0.021 | +0.1684 | 0.1786 | 166% | actual:creator_dump=37, actual:line_broken=64, actual:max_loss=1, actual:migrated=2, actual:target=1, actual:trailing=1, trailing=57 |
| c_trail30 | 163 | 41% | +0.023 | +0.1865 | 0.2218 | 153% | actual:creator_dump=48, actual:line_broken=85, actual:max_loss=2, actual:migrated=2, actual:target=1, actual:time_stop=1, actual:trailing=2, trailing=22 |
| c_trail50 | 163 | 40% | +0.013 | +0.1057 | 0.2569 | 269% | actual:creator_dump=53, actual:line_broken=89, actual:max_loss=5, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, trailing=9 |
| d_arm+25%_trail30 | 163 | 41% | +0.018 | +0.1446 | 0.2468 | 197% | actual:creator_dump=53, actual:line_broken=89, actual:max_loss=11, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, trailing=3 |
| d_arm+50%_trail30 | 163 | 41% | +0.015 | +0.1216 | 0.2683 | 234% | actual:creator_dump=53, actual:line_broken=89, actual:max_loss=13, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, trailing=1 |
| d_arm+100%_trail30 | 163 | 40% | +0.011 | +0.0896 | 0.2683 | 318% | actual:creator_dump=53, actual:line_broken=89, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2 |
| d_arm+25%_trail15 | 163 | 42% | +0.006 | +0.0466 | 0.2057 | 600% | actual:creator_dump=51, actual:line_broken=83, actual:max_loss=11, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=1, trailing=12 |
| d_arm+50%_trail15 | 163 | 41% | +0.000 | +0.0030 | 0.2434 | 9468% | actual:creator_dump=52, actual:line_broken=85, actual:max_loss=13, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=1, trailing=7 |
| d_tp+25%_else_trail30 | 163 | 46% | +0.000 | +0.0008 | 0.1734 | 24455% | actual:creator_dump=34, actual:line_broken=65, actual:max_loss=1, actual:time_stop=1, target=43, trailing=19 |
| d_tp+50%_else_trail30 | 163 | 42% | +0.013 | +0.1068 | 0.2041 | 196% | actual:creator_dump=41, actual:line_broken=73, actual:max_loss=1, actual:time_stop=1, target=26, trailing=21 |
| d_tp+100%_else_trail30 | 163 | 42% | +0.037 | +0.2975 | 0.1804 | 93% | actual:creator_dump=48, actual:line_broken=82, actual:max_loss=1, actual:migrated=1, actual:time_stop=1, actual:trailing=1, target=7, trailing=22 |
| e_time2m | 163 | 40% | -0.008 | -0.0681 | 0.2827 | — | actual:creator_dump=43, actual:line_broken=68, actual:max_loss=13, actual:migrated=2, actual:trailing=2, time_stop=35 |
| e_time5m | 163 | 40% | +0.009 | +0.0764 | 0.2615 | 366% | actual:creator_dump=51, actual:line_broken=81, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:trailing=2, time_stop=12 |
| e_time15m | 163 | 40% | +0.011 | +0.0911 | 0.2683 | 312% | actual:creator_dump=53, actual:line_broken=89, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:trailing=2, time_stop=2 |
| e_time30m | 163 | 40% | +0.011 | +0.0896 | 0.2683 | 318% | actual:creator_dump=53, actual:line_broken=89, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2 |
| f_first_creator_sell | 163 | 39% | +0.004 | +0.0312 | 0.2748 | 912% | actual:creator_dump=39, actual:line_broken=89, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, creator_sell=14 |
| f2_creator_sell_incl_15s_net_seller | 163 | 40% | +0.001 | +0.0095 | 0.2571 | 3011% | actual:creator_dump=22, actual:line_broken=85, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, creator_sell=37 |
| g_tp30_or_trail20_or_5m | 163 | 42% | +0.004 | +0.0316 | 0.1667 | 629% | actual:creator_dump=29, actual:line_broken=59, target=36, time_stop=5, trailing=34 |
| g2_tp30_or_trail20_or_2m | 163 | 42% | -0.002 | -0.0140 | 0.1858 | — | actual:creator_dump=28, actual:line_broken=56, target=33, time_stop=13, trailing=33 |
| g3_tp50_or_trail20_or_5m | 163 | 40% | +0.015 | +0.1234 | 0.1735 | 170% | actual:creator_dump=35, actual:line_broken=62, target=24, time_stop=6, trailing=36 |
| g4_tp30_or_trail15_or_5m | 163 | 41% | +0.009 | +0.0725 | 0.1551 | 274% | actual:creator_dump=26, actual:line_broken=53, target=35, time_stop=3, trailing=46 |
| g5_tp30_or_trail15_or_2m | 163 | 40% | +0.005 | +0.0393 | 0.1741 | 506% | actual:creator_dump=25, actual:line_broken=50, target=33, time_stop=11, trailing=44 |
| h_tp100_or_trail30_or_5m | 163 | 42% | +0.033 | +0.2651 | 0.1804 | 105% | actual:creator_dump=47, actual:line_broken=78, actual:max_loss=1, actual:migrated=1, actual:trailing=1, target=5, time_stop=10, trailing=20 |
| h2_tp100_or_trail30_or_15m | 163 | 42% | +0.037 | +0.2975 | 0.1804 | 93% | actual:creator_dump=48, actual:line_broken=82, actual:max_loss=1, actual:migrated=1, actual:trailing=1, target=7, time_stop=1, trailing=22 |
| h3_tp100_or_trail30_or_30m | 163 | 42% | +0.037 | +0.2975 | 0.1804 | 93% | actual:creator_dump=48, actual:line_broken=82, actual:max_loss=1, actual:migrated=1, actual:time_stop=1, actual:trailing=1, target=7, trailing=22 |
| h4_tp300_or_trail30_or_30m | 163 | 41% | +0.024 | +0.1984 | 0.2218 | 149% | actual:creator_dump=48, actual:line_broken=85, actual:max_loss=2, actual:migrated=2, actual:time_stop=1, actual:trailing=2, target=1, trailing=22 |

## flow_v2/6
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 25 | 16% | +0.007 | +0.0087 | 0.0942 | 1626% | creator_dump=7, line_broken=15, time_stop=3 |
| a2_actual_exit_mcap_fee1.25 | 25 | 16% | +0.009 | +0.0117 | 0.0927 | 1211% | creator_dump=7, line_broken=15, time_stop=3 |
| b_line_broken(2) | 25 | 16% | +0.015 | +0.0189 | 0.0919 | 715% | actual:creator_dump=7, actual:line_broken=6, actual:time_stop=3, line_broken=9 |
| b2_paper_full_set | 25 | 16% | +0.015 | +0.0189 | 0.0918 | 713% | actual:creator_dump=4, actual:line_broken=6, actual:time_stop=3, creator_dump=3, line_broken=9 |
| c_trail15 | 25 | 20% | +0.051 | +0.0638 | 0.0624 | 222% | actual:creator_dump=6, actual:line_broken=12, trailing=7 |
| c_trail30 | 25 | 20% | +0.030 | +0.0375 | 0.0735 | 378% | actual:creator_dump=6, actual:line_broken=14, actual:time_stop=1, trailing=4 |
| c_trail50 | 25 | 16% | +0.010 | +0.0126 | 0.0919 | 1128% | actual:creator_dump=7, actual:line_broken=14, actual:time_stop=3, trailing=1 |
| d_arm+25%_trail30 | 25 | 20% | +0.028 | +0.0354 | 0.0755 | 400% | actual:creator_dump=7, actual:line_broken=14, actual:time_stop=3, trailing=1 |
| d_arm+50%_trail30 | 25 | 20% | +0.028 | +0.0354 | 0.0755 | 400% | actual:creator_dump=7, actual:line_broken=14, actual:time_stop=3, trailing=1 |
| d_arm+100%_trail30 | 25 | 16% | +0.009 | +0.0117 | 0.0927 | 1211% | actual:creator_dump=7, actual:line_broken=15, actual:time_stop=3 |
| d_arm+25%_trail15 | 25 | 20% | +0.028 | +0.0354 | 0.0755 | 400% | actual:creator_dump=7, actual:line_broken=14, actual:time_stop=3, trailing=1 |
| d_arm+50%_trail15 | 25 | 20% | +0.028 | +0.0354 | 0.0755 | 400% | actual:creator_dump=7, actual:line_broken=14, actual:time_stop=3, trailing=1 |
| d_tp+25%_else_trail30 | 25 | 24% | -0.022 | -0.0274 | 0.0624 | — | actual:creator_dump=4, actual:line_broken=11, actual:time_stop=1, target=6, trailing=3 |
| d_tp+50%_else_trail30 | 25 | 20% | +0.000 | +0.0001 | 0.0735 | 60914% | actual:creator_dump=5, actual:line_broken=12, actual:time_stop=1, target=4, trailing=3 |
| d_tp+100%_else_trail30 | 25 | 20% | +0.035 | +0.0443 | 0.0735 | 335% | actual:creator_dump=6, actual:line_broken=13, actual:time_stop=1, target=1, trailing=4 |
| e_time2m | 25 | 16% | -0.027 | -0.0343 | 0.0889 | — | actual:creator_dump=7, actual:line_broken=10, time_stop=8 |
| e_time5m | 25 | 16% | +0.001 | +0.0007 | 0.0905 | 19676% | actual:creator_dump=7, actual:line_broken=14, time_stop=4 |
| e_time15m | 25 | 16% | +0.011 | +0.0136 | 0.0909 | 1042% | actual:creator_dump=7, actual:line_broken=15, time_stop=3 |
| e_time30m | 25 | 16% | +0.009 | +0.0117 | 0.0927 | 1211% | actual:creator_dump=7, actual:line_broken=15, actual:time_stop=3 |
| f_first_creator_sell | 25 | 16% | +0.009 | +0.0118 | 0.0927 | 1206% | actual:creator_dump=4, actual:line_broken=15, actual:time_stop=3, creator_sell=3 |
| f2_creator_sell_incl_15s_net_seller | 25 | 16% | -0.015 | -0.0183 | 0.0904 | — | actual:creator_dump=2, actual:line_broken=15, actual:time_stop=3, creator_sell=5 |
| g_tp30_or_trail20_or_5m | 25 | 20% | -0.013 | -0.0158 | 0.0636 | — | actual:creator_dump=5, actual:line_broken=11, target=5, trailing=4 |
| g2_tp30_or_trail20_or_2m | 25 | 20% | -0.018 | -0.0227 | 0.0634 | — | actual:creator_dump=5, actual:line_broken=9, target=4, time_stop=3, trailing=4 |
| g3_tp50_or_trail20_or_5m | 25 | 20% | +0.010 | +0.0127 | 0.0636 | 691% | actual:creator_dump=5, actual:line_broken=12, target=4, trailing=4 |
| g4_tp30_or_trail15_or_5m | 25 | 20% | -0.002 | -0.0021 | 0.0624 | — | actual:creator_dump=5, actual:line_broken=9, target=5, trailing=6 |
| g5_tp30_or_trail15_or_2m | 25 | 20% | -0.007 | -0.0090 | 0.0622 | — | actual:creator_dump=5, actual:line_broken=7, target=4, time_stop=3, trailing=6 |
| h_tp100_or_trail30_or_5m | 25 | 20% | +0.021 | +0.0263 | 0.0714 | 489% | actual:creator_dump=6, actual:line_broken=13, time_stop=3, trailing=3 |
| h2_tp100_or_trail30_or_15m | 25 | 20% | +0.037 | +0.0460 | 0.0718 | 323% | actual:creator_dump=6, actual:line_broken=13, target=1, time_stop=2, trailing=3 |
| h3_tp100_or_trail30_or_30m | 25 | 20% | +0.035 | +0.0443 | 0.0735 | 335% | actual:creator_dump=6, actual:line_broken=13, actual:time_stop=1, target=1, trailing=4 |
| h4_tp300_or_trail30_or_30m | 25 | 20% | +0.030 | +0.0375 | 0.0735 | 378% | actual:creator_dump=6, actual:line_broken=14, actual:time_stop=1, trailing=4 |

## flow_v2/8
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 31 | 29% | +0.003 | +0.0039 | 0.0891 | 3745% | creator_dump=8, line_broken=19, max_loss=1, time_stop=3 |
| a2_actual_exit_mcap_fee1.25 | 31 | 29% | +0.005 | +0.0075 | 0.0881 | 1962% | creator_dump=8, line_broken=19, max_loss=1, time_stop=3 |
| b_line_broken(2) | 31 | 29% | +0.009 | +0.0133 | 0.0757 | 1028% | actual:creator_dump=8, actual:line_broken=5, actual:max_loss=1, actual:time_stop=3, line_broken=14 |
| b2_paper_full_set | 31 | 32% | +0.013 | +0.0195 | 0.0695 | 701% | actual:creator_dump=5, actual:line_broken=5, actual:time_stop=3, creator_dump=3, line_broken=14, max_loss=1 |
| c_trail15 | 31 | 32% | +0.056 | +0.0867 | 0.0719 | 169% | actual:creator_dump=8, actual:line_broken=15, trailing=8 |
| c_trail30 | 31 | 29% | +0.016 | +0.0252 | 0.0871 | 582% | actual:creator_dump=8, actual:line_broken=17, actual:time_stop=2, trailing=4 |
| c_trail50 | 31 | 29% | +0.007 | +0.0107 | 0.0881 | 1372% | actual:creator_dump=8, actual:line_broken=19, actual:time_stop=3, trailing=1 |
| d_arm+25%_trail30 | 31 | 29% | +0.005 | +0.0075 | 0.0881 | 1962% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=3 |
| d_arm+50%_trail30 | 31 | 29% | +0.005 | +0.0075 | 0.0881 | 1962% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=3 |
| d_arm+100%_trail30 | 31 | 29% | +0.005 | +0.0075 | 0.0881 | 1962% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=3 |
| d_arm+25%_trail15 | 31 | 32% | +0.031 | +0.0476 | 0.0881 | 308% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=2, trailing=1 |
| d_arm+50%_trail15 | 31 | 32% | +0.031 | +0.0476 | 0.0881 | 308% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=2, trailing=1 |
| d_tp+25%_else_trail30 | 31 | 35% | +0.008 | +0.0123 | 0.0871 | 845% | actual:creator_dump=6, actual:line_broken=12, actual:time_stop=1, target=8, trailing=4 |
| d_tp+50%_else_trail30 | 31 | 32% | +0.019 | +0.0292 | 0.0871 | 356% | actual:creator_dump=7, actual:line_broken=14, actual:time_stop=1, target=5, trailing=4 |
| d_tp+100%_else_trail30 | 31 | 29% | +0.021 | +0.0320 | 0.0871 | 480% | actual:creator_dump=8, actual:line_broken=16, actual:time_stop=2, target=1, trailing=4 |
| e_time2m | 31 | 29% | -0.033 | -0.0512 | 0.0879 | — | actual:creator_dump=8, actual:line_broken=15, actual:max_loss=1, actual:time_stop=1, time_stop=6 |
| e_time5m | 31 | 29% | -0.004 | -0.0054 | 0.0880 | — | actual:creator_dump=8, actual:line_broken=18, actual:max_loss=1, actual:time_stop=1, time_stop=3 |
| e_time15m | 31 | 29% | +0.005 | +0.0075 | 0.0881 | 1945% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=1, time_stop=2 |
| e_time30m | 31 | 29% | +0.005 | +0.0075 | 0.0881 | 1962% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=3 |
| f_first_creator_sell | 31 | 32% | +0.007 | +0.0105 | 0.0881 | 1401% | actual:creator_dump=5, actual:line_broken=19, actual:max_loss=1, actual:time_stop=3, creator_sell=3 |
| f2_creator_sell_incl_15s_net_seller | 31 | 29% | -0.018 | -0.0271 | 0.1015 | — | actual:creator_dump=1, actual:line_broken=19, actual:max_loss=1, actual:time_stop=3, creator_sell=7 |
| g_tp30_or_trail20_or_5m | 31 | 32% | +0.011 | +0.0167 | 0.0844 | 623% | actual:creator_dump=7, actual:line_broken=11, target=7, trailing=6 |
| g2_tp30_or_trail20_or_2m | 31 | 32% | +0.006 | +0.0096 | 0.0844 | 1082% | actual:creator_dump=7, actual:line_broken=10, target=6, time_stop=2, trailing=6 |
| g3_tp50_or_trail20_or_5m | 31 | 32% | +0.025 | +0.0381 | 0.0844 | 273% | actual:creator_dump=7, actual:line_broken=13, target=5, trailing=6 |
| g4_tp30_or_trail15_or_5m | 31 | 32% | +0.019 | +0.0292 | 0.0719 | 357% | actual:creator_dump=7, actual:line_broken=10, target=7, trailing=7 |
| g5_tp30_or_trail15_or_2m | 31 | 32% | +0.014 | +0.0221 | 0.0719 | 471% | actual:creator_dump=7, actual:line_broken=9, target=6, time_stop=2, trailing=7 |
| h_tp100_or_trail30_or_5m | 31 | 29% | +0.008 | +0.0122 | 0.0871 | 1098% | actual:creator_dump=8, actual:line_broken=16, actual:time_stop=1, time_stop=2, trailing=4 |
| h2_tp100_or_trail30_or_15m | 31 | 29% | +0.021 | +0.0320 | 0.0871 | 480% | actual:creator_dump=8, actual:line_broken=16, actual:time_stop=1, target=1, time_stop=1, trailing=4 |
| h3_tp100_or_trail30_or_30m | 31 | 29% | +0.021 | +0.0320 | 0.0871 | 480% | actual:creator_dump=8, actual:line_broken=16, actual:time_stop=2, target=1, trailing=4 |
| h4_tp300_or_trail30_or_30m | 31 | 29% | +0.016 | +0.0252 | 0.0871 | 582% | actual:creator_dump=8, actual:line_broken=17, actual:time_stop=2, trailing=4 |

## papel (5 sets)
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 375 | 37% | +0.003 | +0.0554 | 0.5636 | 557% | creator_dump=118, line_broken=209, max_loss=27, migrated=4, target=2, time_stop=11, trailing=4 |
| a2_actual_exit_mcap_fee1.25 | 375 | 37% | +0.005 | +0.0905 | 0.5591 | 342% | creator_dump=118, line_broken=209, max_loss=27, migrated=4, target=2, time_stop=11, trailing=4 |
| b_line_broken(2) | 375 | 36% | -0.003 | -0.0530 | 0.5672 | — | actual:creator_dump=118, actual:line_broken=121, actual:max_loss=27, actual:migrated=2, actual:target=2, actual:time_stop=11, actual:trailing=4, line_broken=90 |
| b2_paper_full_set | 375 | 35% | -0.005 | -0.0950 | 0.5335 | — | actual:creator_dump=82, actual:line_broken=121, actual:max_loss=11, actual:migrated=2, actual:time_stop=11, actual:trailing=4, creator_dump=36, line_broken=90, max_loss=16, target=2 |
| c_trail15 | 375 | 35% | +0.014 | +0.2626 | 0.3868 | 118% | actual:creator_dump=89, actual:line_broken=149, actual:max_loss=2, actual:migrated=4, actual:target=2, actual:trailing=2, trailing=127 |
| c_trail30 | 375 | 38% | +0.016 | +0.3041 | 0.4624 | 102% | actual:creator_dump=109, actual:line_broken=199, actual:max_loss=3, actual:migrated=4, actual:target=2, actual:time_stop=5, actual:trailing=4, trailing=49 |
| c_trail50 | 375 | 37% | +0.007 | +0.1268 | 0.5355 | 244% | actual:creator_dump=118, actual:line_broken=208, actual:max_loss=9, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4, trailing=19 |
| d_arm+25%_trail30 | 375 | 38% | +0.011 | +0.2027 | 0.5139 | 153% | actual:creator_dump=118, actual:line_broken=208, actual:max_loss=22, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4, trailing=6 |
| d_arm+50%_trail30 | 375 | 38% | +0.010 | +0.1783 | 0.5354 | 174% | actual:creator_dump=118, actual:line_broken=208, actual:max_loss=25, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4, trailing=3 |
| d_arm+100%_trail30 | 375 | 37% | +0.005 | +0.0905 | 0.5591 | 342% | actual:creator_dump=118, actual:line_broken=209, actual:max_loss=27, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4 |
| d_arm+25%_trail15 | 375 | 38% | +0.000 | +0.0024 | 0.4486 | 12802% | actual:creator_dump=114, actual:line_broken=195, actual:max_loss=22, actual:migrated=4, actual:target=2, actual:time_stop=10, actual:trailing=2, trailing=26 |
| d_arm+50%_trail15 | 375 | 38% | -0.003 | -0.0549 | 0.5079 | — | actual:creator_dump=116, actual:line_broken=199, actual:max_loss=25, actual:migrated=4, actual:target=2, actual:time_stop=10, actual:trailing=2, trailing=17 |
| d_tp+25%_else_trail30 | 375 | 42% | -0.011 | -0.2094 | 0.4122 | — | actual:creator_dump=78, actual:line_broken=150, actual:max_loss=1, actual:time_stop=4, target=99, trailing=43 |
| d_tp+50%_else_trail30 | 375 | 39% | +0.005 | +0.0875 | 0.4081 | 240% | actual:creator_dump=95, actual:line_broken=169, actual:max_loss=1, actual:time_stop=4, target=60, trailing=46 |
| d_tp+100%_else_trail30 | 375 | 38% | +0.031 | +0.5726 | 0.3797 | 53% | actual:creator_dump=109, actual:line_broken=190, actual:max_loss=1, actual:migrated=2, actual:time_stop=5, actual:trailing=2, target=17, trailing=49 |
| e_time2m | 375 | 36% | -0.019 | -0.3642 | 0.5846 | — | actual:creator_dump=99, actual:line_broken=157, actual:max_loss=25, actual:migrated=4, actual:time_stop=1, actual:trailing=4, time_stop=85 |
| e_time5m | 375 | 37% | +0.004 | +0.0678 | 0.5939 | 457% | actual:creator_dump=115, actual:line_broken=191, actual:max_loss=27, actual:migrated=4, actual:target=2, actual:time_stop=1, actual:trailing=4, time_stop=31 |
| e_time15m | 375 | 37% | +0.005 | +0.0974 | 0.5591 | 318% | actual:creator_dump=118, actual:line_broken=209, actual:max_loss=27, actual:migrated=4, actual:target=2, actual:time_stop=1, actual:trailing=4, time_stop=10 |
| e_time30m | 375 | 37% | +0.005 | +0.0905 | 0.5591 | 342% | actual:creator_dump=118, actual:line_broken=209, actual:max_loss=27, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4 |
| f_first_creator_sell | 375 | 36% | -0.001 | -0.0107 | 0.5718 | — | actual:creator_dump=82, actual:line_broken=209, actual:max_loss=27, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4, creator_sell=36 |
| f2_creator_sell_incl_15s_net_seller | 375 | 36% | -0.007 | -0.1361 | 0.5634 | — | actual:creator_dump=46, actual:line_broken=203, actual:max_loss=23, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4, creator_sell=82 |
| g_tp30_or_trail20_or_5m | 375 | 39% | -0.007 | -0.1305 | 0.4236 | — | actual:creator_dump=71, actual:line_broken=135, target=84, time_stop=9, trailing=76 |
| g2_tp30_or_trail20_or_2m | 375 | 38% | -0.012 | -0.2252 | 0.4356 | — | actual:creator_dump=68, actual:line_broken=126, target=75, time_stop=32, trailing=74 |
| g3_tp50_or_trail20_or_5m | 375 | 37% | +0.006 | +0.1073 | 0.3956 | 196% | actual:creator_dump=84, actual:line_broken=144, target=56, time_stop=11, trailing=80 |
| g4_tp30_or_trail15_or_5m | 375 | 38% | -0.003 | -0.0494 | 0.3913 | — | actual:creator_dump=66, actual:line_broken=120, target=81, time_stop=6, trailing=102 |
| g5_tp30_or_trail15_or_2m | 375 | 37% | -0.006 | -0.1035 | 0.4033 | — | actual:creator_dump=63, actual:line_broken=111, target=75, time_stop=28, trailing=98 |
| h_tp100_or_trail30_or_5m | 375 | 38% | +0.024 | +0.4561 | 0.4261 | 67% | actual:creator_dump=107, actual:line_broken=183, actual:max_loss=1, actual:migrated=2, actual:time_stop=1, actual:trailing=2, target=11, time_stop=24, trailing=44 |
| h2_tp100_or_trail30_or_15m | 375 | 38% | +0.031 | +0.5760 | 0.3797 | 53% | actual:creator_dump=109, actual:line_broken=190, actual:max_loss=1, actual:migrated=2, actual:time_stop=1, actual:trailing=2, target=17, time_stop=6, trailing=47 |
| h3_tp100_or_trail30_or_30m | 375 | 38% | +0.031 | +0.5726 | 0.3797 | 53% | actual:creator_dump=109, actual:line_broken=190, actual:max_loss=1, actual:migrated=2, actual:time_stop=5, actual:trailing=2, target=17, trailing=49 |
| h4_tp300_or_trail30_or_30m | 375 | 38% | +0.017 | +0.3279 | 0.4624 | 102% | actual:creator_dump=109, actual:line_broken=199, actual:max_loss=3, actual:migrated=4, actual:time_stop=5, actual:trailing=4, target=2, trailing=49 |

## papel unico (mint@minuto)
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 215 | 36% | -0.002 | -0.0188 | 0.3069 | — | creator_dump=71, line_broken=118, max_loss=15, migrated=2, target=1, time_stop=6, trailing=2 |
| a2_actual_exit_mcap_fee1.25 | 215 | 36% | +0.000 | +0.0018 | 0.3043 | 16164% | creator_dump=71, line_broken=118, max_loss=15, migrated=2, target=1, time_stop=6, trailing=2 |
| b_line_broken(2) | 215 | 35% | -0.008 | -0.0816 | 0.3079 | — | actual:creator_dump=71, actual:line_broken=66, actual:max_loss=15, actual:migrated=1, actual:target=1, actual:time_stop=6, actual:trailing=2, line_broken=53 |
| b2_paper_full_set | 215 | 35% | -0.009 | -0.0982 | 0.2906 | — | actual:creator_dump=48, actual:line_broken=66, actual:max_loss=6, actual:migrated=1, actual:time_stop=6, actual:trailing=2, creator_dump=23, line_broken=53, max_loss=9, target=1 |
| c_trail15 | 215 | 36% | +0.019 | +0.1996 | 0.2005 | 141% | actual:creator_dump=54, actual:line_broken=85, actual:max_loss=1, actual:migrated=2, actual:target=1, actual:trailing=1, trailing=71 |
| c_trail30 | 215 | 37% | +0.013 | +0.1421 | 0.2333 | 200% | actual:creator_dump=65, actual:line_broken=111, actual:max_loss=2, actual:migrated=2, actual:target=1, actual:time_stop=3, actual:trailing=2, trailing=29 |
| c_trail50 | 215 | 36% | +0.002 | +0.0219 | 0.2920 | 1298% | actual:creator_dump=71, actual:line_broken=117, actual:max_loss=5, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2, trailing=11 |
| d_arm+25%_trail30 | 215 | 37% | +0.007 | +0.0805 | 0.2591 | 354% | actual:creator_dump=71, actual:line_broken=117, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2, trailing=4 |
| d_arm+50%_trail30 | 215 | 37% | +0.005 | +0.0575 | 0.2806 | 495% | actual:creator_dump=71, actual:line_broken=117, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2, trailing=2 |
| d_arm+100%_trail30 | 215 | 36% | +0.000 | +0.0018 | 0.3043 | 16164% | actual:creator_dump=71, actual:line_broken=118, actual:max_loss=15, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2 |
| d_arm+25%_trail15 | 215 | 38% | +0.002 | +0.0226 | 0.2244 | 1248% | actual:creator_dump=69, actual:line_broken=111, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:time_stop=5, actual:trailing=1, trailing=14 |
| d_arm+50%_trail15 | 215 | 38% | -0.002 | -0.0211 | 0.2637 | — | actual:creator_dump=70, actual:line_broken=113, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:time_stop=5, actual:trailing=1, trailing=9 |
| d_tp+25%_else_trail30 | 215 | 42% | -0.005 | -0.0487 | 0.1982 | — | actual:creator_dump=48, actual:line_broken=85, actual:max_loss=1, actual:time_stop=2, target=54, trailing=25 |
| d_tp+50%_else_trail30 | 215 | 39% | +0.008 | +0.0829 | 0.2027 | 252% | actual:creator_dump=57, actual:line_broken=96, actual:max_loss=1, actual:time_stop=2, target=32, trailing=27 |
| d_tp+100%_else_trail30 | 215 | 38% | +0.024 | +0.2599 | 0.1920 | 108% | actual:creator_dump=65, actual:line_broken=107, actual:max_loss=1, actual:migrated=1, actual:time_stop=3, actual:trailing=1, target=8, trailing=29 |
| e_time2m | 215 | 36% | -0.019 | -0.2077 | 0.3395 | — | actual:creator_dump=60, actual:line_broken=90, actual:max_loss=14, actual:migrated=2, actual:time_stop=1, actual:trailing=2, time_stop=46 |
| e_time5m | 215 | 36% | -0.002 | -0.0225 | 0.3191 | — | actual:creator_dump=69, actual:line_broken=109, actual:max_loss=15, actual:migrated=2, actual:target=1, actual:time_stop=1, actual:trailing=2, time_stop=16 |
| e_time15m | 215 | 36% | +0.000 | +0.0052 | 0.3043 | 5479% | actual:creator_dump=71, actual:line_broken=118, actual:max_loss=15, actual:migrated=2, actual:target=1, actual:time_stop=1, actual:trailing=2, time_stop=5 |
| e_time30m | 215 | 36% | +0.000 | +0.0018 | 0.3043 | 16164% | actual:creator_dump=71, actual:line_broken=118, actual:max_loss=15, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2 |
| f_first_creator_sell | 215 | 36% | -0.004 | -0.0460 | 0.3105 | — | actual:creator_dump=48, actual:line_broken=118, actual:max_loss=15, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2, creator_sell=23 |
| f2_creator_sell_incl_15s_net_seller | 215 | 36% | -0.009 | -0.1016 | 0.3020 | — | actual:creator_dump=27, actual:line_broken=114, actual:max_loss=13, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2, creator_sell=50 |
| g_tp30_or_trail20_or_5m | 215 | 39% | +0.001 | +0.0072 | 0.2078 | 2800% | actual:creator_dump=44, actual:line_broken=77, target=46, time_stop=5, trailing=43 |
| g2_tp30_or_trail20_or_2m | 215 | 38% | -0.004 | -0.0448 | 0.2267 | — | actual:creator_dump=42, actual:line_broken=72, target=42, time_stop=17, trailing=42 |
| g3_tp50_or_trail20_or_5m | 215 | 37% | +0.011 | +0.1163 | 0.1895 | 180% | actual:creator_dump=51, actual:line_broken=83, target=30, time_stop=6, trailing=45 |
| g4_tp30_or_trail15_or_5m | 215 | 38% | +0.006 | +0.0668 | 0.1899 | 301% | actual:creator_dump=41, actual:line_broken=68, target=45, time_stop=3, trailing=58 |
| g5_tp30_or_trail15_or_2m | 215 | 37% | +0.003 | +0.0272 | 0.2088 | 740% | actual:creator_dump=39, actual:line_broken=63, target=42, time_stop=15, trailing=56 |
| h_tp100_or_trail30_or_5m | 215 | 38% | +0.019 | +0.2094 | 0.2136 | 133% | actual:creator_dump=64, actual:line_broken=103, actual:max_loss=1, actual:migrated=1, actual:time_stop=1, actual:trailing=1, target=5, time_stop=13, trailing=26 |
| h2_tp100_or_trail30_or_15m | 215 | 38% | +0.024 | +0.2616 | 0.1920 | 107% | actual:creator_dump=65, actual:line_broken=107, actual:max_loss=1, actual:migrated=1, actual:time_stop=1, actual:trailing=1, target=8, time_stop=3, trailing=28 |
| h3_tp100_or_trail30_or_30m | 215 | 38% | +0.024 | +0.2599 | 0.1920 | 108% | actual:creator_dump=65, actual:line_broken=107, actual:max_loss=1, actual:migrated=1, actual:time_stop=3, actual:trailing=1, target=8, trailing=29 |
| h4_tp300_or_trail30_or_30m | 215 | 37% | +0.014 | +0.1540 | 0.2333 | 193% | actual:creator_dump=65, actual:line_broken=111, actual:max_loss=2, actual:migrated=2, actual:time_stop=3, actual:trailing=2, target=1, trailing=29 |

## as posicoes reais, aposta a aposta (PnL a 0,05 SOL, taxas 1,25 %)
| mint | cobertura | a_actual_recorded | b_line_broken(2) | c_trail15 | c_trail30 | e_time2m | e_time5m | f_first_creator_sell | g_tp30_or_trail20_or_5m | g5_tp30_or_trail15_or_2m |
|---|---|---|---|---|---|---|---|---|---|---|
| 7s4dKmpv | 39s | -0.0093 (creator_dump, 48s) | -0.0075 (actual:creator_dump, 48s) | -0.0075 (actual:creator_dump, 48s) | -0.0075 (actual:creator_dump, 48s) | -0.0075 (actual:creator_dump, 48s) | -0.0075 (actual:creator_dump, 48s) | -0.0075 (actual:creator_dump, 48s) | -0.0075 (actual:creator_dump, 48s) | -0.0075 (actual:creator_dump, 48s) |
| 63NPcW9q | 46s | -0.0035 (creator_dump, 52s) | -0.0017 (line_broken, 31s) | -0.0027 (actual:creator_dump, 52s) | -0.0027 (actual:creator_dump, 52s) | -0.0027 (actual:creator_dump, 52s) | -0.0027 (actual:creator_dump, 52s) | -0.0026 (creator_sell, 46s) | -0.0027 (actual:creator_dump, 52s) | -0.0027 (actual:creator_dump, 52s) |
| CCLstvwa | 394s | -0.0071 (trailing, 396s) | -0.0121 (line_broken, 56s) | -0.0105 (trailing, 24s) | -0.0063 (trailing, 394s) | -0.0119 (time_stop, 121s) | +0.0137 (time_stop, 314s) | -0.0064 (actual:trailing, 396s) | -0.0121 (trailing, 40s) | -0.0105 (trailing, 24s) |
| 2hhJXPy3 | 1557s | -0.0176 (time_stop, 1800s) | -0.0170 (actual:time_stop, 1800s) | -0.0108 (trailing, 20s) | -0.0168 (trailing, 1366s) | -0.0151 (time_stop, 132s) | -0.0152 (time_stop, 307s) | -0.0170 (actual:time_stop, 1800s) | -0.0135 (trailing, 52s) | -0.0108 (trailing, 20s) |
| Dy9YAbcL | 514s | -0.0059 (creator_dump, 514s) | +0.0116 (line_broken, 204s) | +0.0025 (trailing, 338s) | -0.0051 (trailing, 449s) | +0.0139 (time_stop, 124s) | +0.0066 (time_stop, 306s) | -0.0052 (creator_sell, 465s) | +0.0133 (target, 93s) | +0.0133 (target, 93s) |
| GdZ5hSdz | 80s | -0.0038 (creator_dump, 86s) | -0.0030 (actual:creator_dump, 86s) | -0.0030 (actual:creator_dump, 86s) | -0.0030 (actual:creator_dump, 86s) | -0.0030 (actual:creator_dump, 86s) | -0.0030 (actual:creator_dump, 86s) | -0.0030 (actual:creator_dump, 86s) | -0.0030 (actual:creator_dump, 86s) | -0.0030 (actual:creator_dump, 86s) |
| 6zdT1MxC | 104s | +0.0329 (creator_dump, 117s) | +0.0343 (actual:creator_dump, 117s) | +0.0343 (actual:creator_dump, 117s) | +0.0343 (actual:creator_dump, 117s) | +0.0343 (actual:creator_dump, 117s) | +0.0343 (actual:creator_dump, 117s) | +0.0180 (creator_sell, 55s) | +0.0150 (target, 39s) | +0.0150 (target, 39s) |
| rYJYP8jV | 42s | -0.0040 (creator_dump, 45s) | -0.0032 (actual:creator_dump, 45s) | -0.0032 (actual:creator_dump, 45s) | -0.0032 (actual:creator_dump, 45s) | -0.0032 (actual:creator_dump, 45s) | -0.0032 (actual:creator_dump, 45s) | -0.0031 (creator_sell, 42s) | -0.0032 (actual:creator_dump, 45s) | -0.0032 (actual:creator_dump, 45s) |
| M3kpWCVA | 1586s | -0.0122 (time_stop, 1804s) | -0.0078 (line_broken, 31s) | -0.0093 (trailing, 63s) | -0.0115 (actual:time_stop, 1804s) | -0.0109 (time_stop, 129s) | -0.0044 (time_stop, 308s) | -0.0115 (actual:time_stop, 1804s) | -0.0044 (time_stop, 308s) | -0.0093 (trailing, 63s) |
| 8DqtPVgJ | 28s | -0.0025 (creator_dump, 33s) | -0.0017 (actual:creator_dump, 33s) | -0.0017 (actual:creator_dump, 33s) | -0.0017 (actual:creator_dump, 33s) | -0.0017 (actual:creator_dump, 33s) | -0.0017 (actual:creator_dump, 33s) | -0.0017 (actual:creator_dump, 33s) | -0.0017 (actual:creator_dump, 33s) | -0.0017 (actual:creator_dump, 33s) |
| 4c3rRxkp | 1738s | -0.0029 (time_stop, 1804s) | -0.0019 (line_broken, 124s) | -0.0021 (actual:time_stop, 1804s) | -0.0021 (actual:time_stop, 1804s) | -0.0019 (time_stop, 124s) | -0.0019 (time_stop, 315s) | -0.0021 (actual:time_stop, 1804s) | -0.0019 (time_stop, 315s) | -0.0019 (time_stop, 124s) |
| ADxEynfQ | 36s | -0.0383 (trailing, 43s) | -0.0380 (actual:trailing, 43s) | -0.0380 (actual:trailing, 43s) | -0.0380 (actual:trailing, 43s) | -0.0380 (actual:trailing, 43s) | -0.0380 (actual:trailing, 43s) | -0.0380 (actual:trailing, 43s) | -0.0380 (actual:trailing, 43s) | -0.0380 (actual:trailing, 43s) |

## top-3 contribuintes (papel unico)
- a2_actual_exit_mcap_fee1.25: soma +0.0018; top3 = 4XYuRzrB +0.1184 (creator_dump, 0s); fsnuqm67 +0.0957 (target, 0s); H88Srjvu +0.0707 (line_broken, 0s)
- c_trail15: soma +0.1996; top3 = 4XYuRzrB +0.1184 (actual:creator_dump, 52s); fsnuqm67 +0.0957 (actual:target, 201s); 5hmWwRNw +0.0673 (actual:creator_dump, 49s)
- c_trail30: soma +0.1421; top3 = 4XYuRzrB +0.1184 (actual:creator_dump, 52s); fsnuqm67 +0.0957 (actual:target, 201s); H88Srjvu +0.0707 (actual:line_broken, 623s)
- d_tp+100%_else_trail30: soma +0.2599; top3 = 4XYuRzrB +0.1184 (actual:creator_dump, 52s); fsnuqm67 +0.0939 (target, 132s); 5hmWwRNw +0.0673 (actual:creator_dump, 49s)
- e_time5m: soma -0.0225; top3 = 4XYuRzrB +0.1184 (actual:creator_dump, 52s); fsnuqm67 +0.0957 (actual:target, 201s); 5hmWwRNw +0.0673 (actual:creator_dump, 49s)

## ranking (soma SOL, top3 < 50 %)
- papel (5 sets): melhor com top3<50%: nenhuma | melhor absoluta: h2_tp100_or_trail30_or_15m (+0.5760, top3 53%)
- papel unico (mint@minuto): melhor com top3<50%: nenhuma | melhor absoluta: h2_tp100_or_trail30_or_15m (+0.2616, top3 107%)
- operator/5 real: melhor com top3<50%: nenhuma | melhor absoluta: e_time5m (-0.0230, top3 nan%)
- operator/5: melhor com top3<50%: nenhuma | melhor absoluta: e_time5m (+0.0230, top3 544%)
- flow_v2/5: melhor com top3<50%: nenhuma | melhor absoluta: d_tp+100%_else_trail30 (+0.1875, top3 115%)
- flow_v2/2: melhor com top3<50%: nenhuma | melhor absoluta: d_tp+100%_else_trail30 (+0.2975, top3 93%)
- flow_v2/6: melhor com top3<50%: nenhuma | melhor absoluta: c_trail15 (+0.0638, top3 222%)
- flow_v2/8: melhor com top3<50%: nenhuma | melhor absoluta: c_trail15 (+0.0867, top3 169%)

## delta pareado por aposta (regra - saida registrada a 1,25 %), modo=earlier

### papel unico (mint@minuto) (n=215)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 21 | 24 | 170 | +0.0000 | -0.0833 | 64% | 0.77 |
| b2_paper_full_set | 41 | 32 | 142 | +0.0000 | -0.1000 | 40% | 0.35 |
| c_trail15 | 44 | 26 | 145 | +0.0000 | +0.1979 | 22% | 0.04 |
| c_trail30 | 26 | 3 | 186 | +0.0000 | +0.1404 | 50% | 0.00 |
| c_trail50 | 8 | 2 | 205 | +0.0000 | +0.0202 | 89% | 0.11 |
| d_arm+25%_trail30 | 4 | 0 | 211 | +0.0000 | +0.0787 | 98% | 0.12 |
| d_arm+50%_trail30 | 2 | 0 | 213 | +0.0000 | +0.0557 | 100% | 0.50 |
| d_arm+100%_trail30 | 0 | 0 | 215 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 7 | 7 | 201 | +0.0000 | +0.0208 | 61% | 1.00 |
| d_arm+50%_trail15 | 4 | 5 | 206 | +0.0000 | -0.0228 | 80% | 1.00 |
| d_tp+25%_else_trail30 | 45 | 34 | 136 | +0.0000 | -0.0505 | 29% | 0.26 |
| d_tp+50%_else_trail30 | 39 | 20 | 156 | +0.0000 | +0.0811 | 41% | 0.02 |
| d_tp+100%_else_trail30 | 30 | 7 | 178 | +0.0000 | +0.2581 | 49% | 0.00 |
| e_time2m | 24 | 20 | 171 | +0.0000 | -0.2094 | 41% | 0.65 |
| e_time5m | 10 | 6 | 199 | +0.0000 | -0.0242 | 74% | 0.45 |
| e_time15m | 3 | 0 | 212 | +0.0000 | +0.0034 | 100% | 0.25 |
| e_time30m | 0 | 0 | 215 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 12 | 6 | 197 | +0.0000 | -0.0478 | 64% | 0.24 |
| f2_creator_sell_incl_15s_net_seller | 32 | 14 | 169 | +0.0000 | -0.1033 | 34% | 0.01 |
| g_tp30_or_trail20_or_5m | 51 | 42 | 122 | +0.0000 | +0.0054 | 25% | 0.41 |
| g2_tp30_or_trail20_or_2m | 57 | 42 | 116 | +0.0000 | -0.0466 | 24% | 0.16 |
| g3_tp50_or_trail20_or_5m | 46 | 34 | 135 | +0.0000 | +0.1145 | 30% | 0.22 |
| g4_tp30_or_trail15_or_5m | 57 | 48 | 110 | +0.0000 | +0.0651 | 22% | 0.44 |
| g5_tp30_or_trail15_or_2m | 64 | 47 | 104 | +0.0000 | +0.0254 | 21% | 0.13 |
| h_tp100_or_trail30_or_5m | 33 | 11 | 171 | +0.0000 | +0.2077 | 43% | 0.00 |
| h2_tp100_or_trail30_or_15m | 30 | 7 | 178 | +0.0000 | +0.2598 | 48% | 0.00 |
| h3_tp100_or_trail30_or_30m | 30 | 7 | 178 | +0.0000 | +0.2581 | 49% | 0.00 |
| h4_tp300_or_trail30_or_30m | 27 | 3 | 185 | +0.0000 | +0.1523 | 46% | 0.00 |

### operator/5 real (n=12)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 4 | 1 | 7 | +0.0000 | +0.0160 | 99% | 0.38 |
| b2_paper_full_set | 5 | 2 | 5 | +0.0000 | -0.0003 | 98% | 0.45 |
| c_trail15 | 3 | 1 | 8 | +0.0000 | +0.0120 | 100% | 0.62 |
| c_trail30 | 3 | 0 | 9 | +0.0000 | +0.0003 | 100% | 0.25 |
| c_trail50 | 0 | 0 | 12 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail30 | 2 | 0 | 10 | +0.0000 | +0.0002 | 100% | 0.50 |
| d_arm+50%_trail30 | 0 | 0 | 12 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+100%_trail30 | 0 | 0 | 12 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 2 | 0 | 10 | +0.0000 | +0.0157 | 100% | 0.50 |
| d_arm+50%_trail15 | 0 | 0 | 12 | +0.0000 | +0.0000 | nan% | nan |
| d_tp+25%_else_trail30 | 3 | 1 | 8 | +0.0000 | +0.0205 | 100% | 0.62 |
| d_tp+50%_else_trail30 | 4 | 0 | 8 | +0.0000 | +0.0032 | 98% | 0.12 |
| d_tp+100%_else_trail30 | 3 | 0 | 9 | +0.0000 | +0.0003 | 100% | 0.25 |
| e_time2m | 4 | 1 | 7 | +0.0000 | +0.0163 | 99% | 0.38 |
| e_time5m | 5 | 0 | 7 | +0.0000 | +0.0409 | 95% | 0.06 |
| e_time15m | 3 | 0 | 9 | +0.0000 | +0.0021 | 100% | 0.25 |
| e_time30m | 0 | 0 | 12 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 2 | 2 | 8 | +0.0000 | -0.0161 | 100% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 3 | 2 | 7 | +0.0000 | -0.0137 | 100% | 1.00 |
| g_tp30_or_trail20_or_5m | 4 | 2 | 6 | +0.0000 | +0.0041 | 99% | 0.69 |
| g2_tp30_or_trail20_or_2m | 4 | 2 | 6 | +0.0000 | -0.0023 | 99% | 0.69 |
| g3_tp50_or_trail20_or_5m | 5 | 1 | 6 | +0.0000 | +0.0196 | 88% | 0.22 |
| g4_tp30_or_trail15_or_5m | 4 | 2 | 6 | +0.0000 | +0.0036 | 99% | 0.69 |
| g5_tp30_or_trail15_or_2m | 4 | 2 | 6 | +0.0000 | +0.0036 | 99% | 0.69 |
| h_tp100_or_trail30_or_5m | 5 | 0 | 7 | +0.0000 | +0.0409 | 95% | 0.06 |
| h2_tp100_or_trail30_or_15m | 5 | 0 | 7 | +0.0000 | +0.0023 | 92% | 0.06 |
| h3_tp100_or_trail30_or_30m | 3 | 0 | 9 | +0.0000 | +0.0003 | 100% | 0.25 |
| h4_tp300_or_trail30_or_30m | 3 | 0 | 9 | +0.0000 | +0.0003 | 100% | 0.25 |

### operator/5 (n=19)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 2 | 3 | 14 | +0.0000 | +0.0260 | 100% | 1.00 |
| b2_paper_full_set | 5 | 3 | 11 | +0.0000 | +0.0335 | 99% | 0.73 |
| c_trail15 | 3 | 3 | 13 | +0.0000 | -0.0426 | 100% | 1.00 |
| c_trail30 | 1 | 0 | 18 | +0.0000 | +0.0001 | 100% | 1.00 |
| c_trail50 | 0 | 0 | 19 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail30 | 0 | 0 | 19 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+50%_trail30 | 0 | 0 | 19 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+100%_trail30 | 0 | 0 | 19 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 0 | 1 | 18 | +0.0000 | -0.0360 | nan% | 1.00 |
| d_arm+50%_trail15 | 0 | 1 | 18 | +0.0000 | -0.0360 | nan% | 1.00 |
| d_tp+25%_else_trail30 | 3 | 2 | 14 | +0.0000 | -0.0386 | 100% | 1.00 |
| d_tp+50%_else_trail30 | 2 | 1 | 16 | +0.0000 | -0.0026 | 100% | 1.00 |
| d_tp+100%_else_trail30 | 2 | 0 | 17 | +0.0000 | +0.0331 | 100% | 0.50 |
| e_time2m | 3 | 2 | 14 | +0.0000 | -0.0365 | 100% | 1.00 |
| e_time5m | 2 | 0 | 17 | +0.0000 | +0.0448 | 100% | 0.50 |
| e_time15m | 1 | 0 | 18 | +0.0000 | +0.0018 | 100% | 1.00 |
| e_time30m | 0 | 0 | 19 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 3 | 0 | 16 | +0.0000 | +0.0075 | 100% | 0.25 |
| f2_creator_sell_incl_15s_net_seller | 5 | 0 | 14 | +0.0000 | +0.0095 | 90% | 0.06 |
| g_tp30_or_trail20_or_5m | 4 | 3 | 12 | +0.0000 | -0.0258 | 87% | 1.00 |
| g2_tp30_or_trail20_or_2m | 4 | 4 | 11 | +0.0000 | -0.0394 | 94% | 1.00 |
| g3_tp50_or_trail20_or_5m | 2 | 3 | 14 | +0.0000 | -0.0014 | 100% | 1.00 |
| g4_tp30_or_trail15_or_5m | 5 | 3 | 11 | +0.0000 | -0.0385 | 80% | 0.73 |
| g5_tp30_or_trail15_or_2m | 6 | 3 | 10 | +0.0000 | -0.0379 | 78% | 0.51 |
| h_tp100_or_trail30_or_5m | 2 | 0 | 17 | +0.0000 | +0.0348 | 100% | 0.50 |
| h2_tp100_or_trail30_or_15m | 2 | 0 | 17 | +0.0000 | +0.0348 | 100% | 0.50 |
| h3_tp100_or_trail30_or_30m | 2 | 0 | 17 | +0.0000 | +0.0331 | 100% | 0.50 |
| h4_tp300_or_trail30_or_30m | 1 | 0 | 18 | +0.0000 | +0.0001 | 100% | 1.00 |

### flow_v2/5 (n=137)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 6 | 15 | 116 | +0.0000 | -0.0926 | 97% | 0.08 |
| b2_paper_full_set | 17 | 22 | 98 | +0.0000 | -0.1180 | 60% | 0.52 |
| c_trail15 | 25 | 23 | 89 | +0.0000 | +0.0046 | 36% | 0.89 |
| c_trail30 | 15 | 3 | 119 | +0.0000 | +0.0731 | 63% | 0.01 |
| c_trail50 | 5 | 2 | 130 | +0.0000 | +0.0161 | 100% | 0.45 |
| d_arm+25%_trail30 | 2 | 0 | 135 | +0.0000 | +0.0335 | 100% | 0.50 |
| d_arm+50%_trail30 | 1 | 0 | 136 | +0.0000 | +0.0320 | 100% | 1.00 |
| d_arm+100%_trail30 | 0 | 0 | 137 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 4 | 7 | 126 | +0.0000 | -0.0729 | 98% | 0.55 |
| d_arm+50%_trail15 | 2 | 5 | 130 | +0.0000 | -0.0867 | 100% | 0.45 |
| d_tp+25%_else_trail30 | 26 | 28 | 83 | +0.0000 | -0.1382 | 41% | 0.89 |
| d_tp+50%_else_trail30 | 23 | 17 | 97 | +0.0000 | -0.0277 | 61% | 0.43 |
| d_tp+100%_else_trail30 | 18 | 7 | 112 | +0.0000 | +0.1840 | 64% | 0.04 |
| e_time2m | 13 | 15 | 109 | +0.0000 | -0.1559 | 54% | 0.85 |
| e_time5m | 5 | 5 | 127 | +0.0000 | -0.0304 | 91% | 1.00 |
| e_time15m | 1 | 0 | 136 | +0.0000 | +0.0015 | 100% | 1.00 |
| e_time30m | 0 | 0 | 137 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 5 | 5 | 127 | +0.0000 | -0.0534 | 100% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 13 | 11 | 113 | +0.0000 | -0.0914 | 53% | 0.84 |
| g_tp30_or_trail20_or_5m | 29 | 35 | 73 | +0.0000 | -0.1189 | 34% | 0.53 |
| g2_tp30_or_trail20_or_2m | 32 | 34 | 71 | +0.0000 | -0.1405 | 33% | 0.90 |
| g3_tp50_or_trail20_or_5m | 27 | 29 | 81 | +0.0000 | -0.0472 | 44% | 0.89 |
| g4_tp30_or_trail15_or_5m | 31 | 40 | 66 | +0.0000 | -0.0922 | 31% | 0.34 |
| g5_tp30_or_trail15_or_2m | 35 | 38 | 64 | +0.0000 | -0.0996 | 30% | 0.82 |
| h_tp100_or_trail30_or_5m | 20 | 10 | 107 | +0.0000 | +0.1361 | 56% | 0.10 |
| h2_tp100_or_trail30_or_15m | 18 | 7 | 112 | +0.0000 | +0.1840 | 64% | 0.04 |
| h3_tp100_or_trail30_or_30m | 18 | 7 | 112 | +0.0000 | +0.1840 | 64% | 0.04 |
| h4_tp300_or_trail30_or_30m | 16 | 3 | 118 | +0.0000 | +0.0849 | 56% | 0.00 |

### flow_v2/2 (n=163)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 11 | 18 | 134 | +0.0000 | -0.0900 | 80% | 0.26 |
| b2_paper_full_set | 25 | 26 | 112 | +0.0000 | -0.1204 | 53% | 1.00 |
| c_trail15 | 31 | 25 | 107 | +0.0000 | +0.0788 | 28% | 0.50 |
| c_trail30 | 19 | 3 | 141 | +0.0000 | +0.0969 | 59% | 0.00 |
| c_trail50 | 6 | 2 | 155 | +0.0000 | +0.0161 | 100% | 0.29 |
| d_arm+25%_trail30 | 3 | 0 | 160 | +0.0000 | +0.0550 | 100% | 0.25 |
| d_arm+50%_trail30 | 1 | 0 | 162 | +0.0000 | +0.0320 | 100% | 1.00 |
| d_arm+100%_trail30 | 0 | 0 | 163 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 5 | 7 | 151 | +0.0000 | -0.0430 | 84% | 0.77 |
| d_arm+50%_trail15 | 2 | 5 | 156 | +0.0000 | -0.0867 | 100% | 0.45 |
| d_tp+25%_else_trail30 | 33 | 29 | 101 | +0.0000 | -0.0888 | 35% | 0.70 |
| d_tp+50%_else_trail30 | 30 | 17 | 116 | +0.0000 | +0.0171 | 51% | 0.08 |
| d_tp+100%_else_trail30 | 22 | 7 | 134 | +0.0000 | +0.2079 | 58% | 0.01 |
| e_time2m | 16 | 17 | 130 | +0.0000 | -0.1577 | 44% | 1.00 |
| e_time5m | 7 | 5 | 151 | +0.0000 | -0.0132 | 75% | 0.77 |
| e_time15m | 1 | 0 | 162 | +0.0000 | +0.0015 | 100% | 1.00 |
| e_time30m | 0 | 0 | 163 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 7 | 6 | 150 | +0.0000 | -0.0584 | 92% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 21 | 12 | 130 | +0.0000 | -0.0802 | 41% | 0.16 |
| g_tp30_or_trail20_or_5m | 37 | 37 | 89 | +0.0000 | -0.0580 | 29% | 1.00 |
| g2_tp30_or_trail20_or_2m | 40 | 37 | 86 | +0.0000 | -0.1036 | 28% | 0.82 |
| g3_tp50_or_trail20_or_5m | 35 | 30 | 98 | +0.0000 | +0.0338 | 35% | 0.62 |
| g4_tp30_or_trail15_or_5m | 40 | 43 | 80 | +0.0000 | -0.0171 | 26% | 0.83 |
| g5_tp30_or_trail15_or_2m | 44 | 42 | 77 | +0.0000 | -0.0503 | 25% | 0.91 |
| h_tp100_or_trail30_or_5m | 25 | 10 | 128 | +0.0000 | +0.1755 | 49% | 0.02 |
| h2_tp100_or_trail30_or_15m | 22 | 7 | 134 | +0.0000 | +0.2079 | 58% | 0.01 |
| h3_tp100_or_trail30_or_30m | 22 | 7 | 134 | +0.0000 | +0.2079 | 58% | 0.01 |
| h4_tp300_or_trail30_or_30m | 20 | 3 | 140 | +0.0000 | +0.1088 | 53% | 0.00 |

### flow_v2/6 (n=25)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 7 | 1 | 17 | +0.0000 | +0.0072 | 100% | 0.07 |
| b2_paper_full_set | 8 | 1 | 16 | +0.0000 | +0.0072 | 99% | 0.04 |
| c_trail15 | 6 | 1 | 18 | +0.0000 | +0.0521 | 74% | 0.12 |
| c_trail30 | 4 | 0 | 21 | +0.0000 | +0.0258 | 100% | 0.12 |
| c_trail50 | 1 | 0 | 24 | +0.0000 | +0.0009 | 100% | 1.00 |
| d_arm+25%_trail30 | 1 | 0 | 24 | +0.0000 | +0.0237 | 100% | 1.00 |
| d_arm+50%_trail30 | 1 | 0 | 24 | +0.0000 | +0.0237 | 100% | 1.00 |
| d_arm+100%_trail30 | 0 | 0 | 25 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 1 | 0 | 24 | +0.0000 | +0.0237 | 100% | 1.00 |
| d_arm+50%_trail15 | 1 | 0 | 24 | +0.0000 | +0.0237 | 100% | 1.00 |
| d_tp+25%_else_trail30 | 5 | 4 | 16 | +0.0000 | -0.0392 | 99% | 1.00 |
| d_tp+50%_else_trail30 | 4 | 3 | 18 | +0.0000 | -0.0116 | 100% | 1.00 |
| d_tp+100%_else_trail30 | 5 | 0 | 20 | +0.0000 | +0.0326 | 99% | 0.06 |
| e_time2m | 6 | 2 | 17 | +0.0000 | -0.0460 | 84% | 0.29 |
| e_time5m | 3 | 1 | 21 | +0.0000 | -0.0111 | 100% | 0.62 |
| e_time15m | 2 | 0 | 23 | +0.0000 | +0.0019 | 100% | 0.50 |
| e_time30m | 0 | 0 | 25 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 1 | 0 | 24 | +0.0000 | +0.0000 | 100% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 4 | 1 | 20 | +0.0000 | -0.0300 | 99% | 0.38 |
| g_tp30_or_trail20_or_5m | 5 | 4 | 16 | +0.0000 | -0.0275 | 91% | 1.00 |
| g2_tp30_or_trail20_or_2m | 7 | 4 | 14 | +0.0000 | -0.0344 | 91% | 0.55 |
| g3_tp50_or_trail20_or_5m | 5 | 3 | 17 | +0.0000 | +0.0010 | 92% | 0.73 |
| g4_tp30_or_trail15_or_5m | 6 | 5 | 14 | +0.0000 | -0.0139 | 80% | 1.00 |
| g5_tp30_or_trail15_or_2m | 8 | 5 | 12 | +0.0000 | -0.0208 | 80% | 0.58 |
| h_tp100_or_trail30_or_5m | 5 | 1 | 19 | +0.0000 | +0.0145 | 98% | 0.22 |
| h2_tp100_or_trail30_or_15m | 5 | 0 | 20 | +0.0000 | +0.0343 | 94% | 0.06 |
| h3_tp100_or_trail30_or_30m | 5 | 0 | 20 | +0.0000 | +0.0326 | 99% | 0.06 |
| h4_tp300_or_trail30_or_30m | 4 | 0 | 21 | +0.0000 | +0.0258 | 100% | 0.12 |

### flow_v2/8 (n=31)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 8 | 5 | 18 | +0.0000 | +0.0059 | 86% | 0.58 |
| b2_paper_full_set | 10 | 5 | 16 | +0.0000 | +0.0121 | 70% | 0.30 |
| c_trail15 | 8 | 0 | 23 | +0.0000 | +0.0792 | 82% | 0.01 |
| c_trail30 | 4 | 0 | 27 | +0.0000 | +0.0177 | 100% | 0.12 |
| c_trail50 | 1 | 0 | 30 | +0.0000 | +0.0032 | 100% | 1.00 |
| d_arm+25%_trail30 | 0 | 0 | 31 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+50%_trail30 | 0 | 0 | 31 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+100%_trail30 | 0 | 0 | 31 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 1 | 0 | 30 | +0.0000 | +0.0401 | 100% | 1.00 |
| d_arm+50%_trail15 | 1 | 0 | 30 | +0.0000 | +0.0401 | 100% | 1.00 |
| d_tp+25%_else_trail30 | 7 | 5 | 19 | +0.0000 | +0.0049 | 96% | 0.77 |
| d_tp+50%_else_trail30 | 6 | 3 | 22 | +0.0000 | +0.0218 | 97% | 0.51 |
| d_tp+100%_else_trail30 | 5 | 0 | 26 | +0.0000 | +0.0245 | 96% | 0.06 |
| e_time2m | 3 | 3 | 25 | +0.0000 | -0.0587 | 100% | 1.00 |
| e_time5m | 2 | 1 | 28 | +0.0000 | -0.0129 | 100% | 1.00 |
| e_time15m | 1 | 0 | 30 | +0.0000 | +0.0001 | 100% | 1.00 |
| e_time30m | 0 | 0 | 31 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 1 | 0 | 30 | +0.0000 | +0.0030 | 100% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 5 | 2 | 24 | +0.0000 | -0.0346 | 95% | 0.45 |
| g_tp30_or_trail20_or_5m | 9 | 4 | 18 | +0.0000 | +0.0092 | 86% | 0.27 |
| g2_tp30_or_trail20_or_2m | 10 | 4 | 17 | +0.0000 | +0.0022 | 86% | 0.18 |
| g3_tp50_or_trail20_or_5m | 8 | 3 | 20 | +0.0000 | +0.0307 | 89% | 0.23 |
| g4_tp30_or_trail15_or_5m | 10 | 4 | 17 | +0.0000 | +0.0217 | 79% | 0.18 |
| g5_tp30_or_trail15_or_2m | 11 | 4 | 16 | +0.0000 | +0.0147 | 79% | 0.12 |
| h_tp100_or_trail30_or_5m | 5 | 1 | 25 | +0.0000 | +0.0047 | 97% | 0.22 |
| h2_tp100_or_trail30_or_15m | 5 | 0 | 26 | +0.0000 | +0.0245 | 96% | 0.06 |
| h3_tp100_or_trail30_or_30m | 5 | 0 | 26 | +0.0000 | +0.0245 | 96% | 0.06 |
| h4_tp300_or_trail30_or_30m | 4 | 0 | 27 | +0.0000 | +0.0177 | 100% | 0.12 |
