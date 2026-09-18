## cobertura
modo=earlier min_cover=1s taxa=1.25% por perna
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
| a2_actual_exit_mcap_fee1.25 | 12 | 8% | -0.098 | -0.0585 | 0.0585 | — | creator_dump=7, time_stop=3, trailing=2 |
| b_line_broken(2) | 12 | 17% | -0.071 | -0.0424 | 0.0507 | — | actual:creator_dump=5, actual:time_stop=1, actual:trailing=1, line_broken=5 |
| b2_paper_full_set | 12 | 17% | -0.098 | -0.0588 | 0.0588 | — | actual:creator_dump=3, actual:time_stop=1, actual:trailing=1, creator_dump=2, line_broken=5 |
| c_trail15 | 12 | 17% | -0.077 | -0.0464 | 0.0524 | — | actual:creator_dump=6, actual:time_stop=1, actual:trailing=1, trailing=4 |
| c_trail30 | 12 | 8% | -0.097 | -0.0582 | 0.0582 | — | actual:creator_dump=6, actual:time_stop=2, actual:trailing=1, trailing=3 |
| c_trail50 | 12 | 8% | -0.098 | -0.0585 | 0.0585 | — | actual:creator_dump=7, actual:time_stop=3, actual:trailing=2 |
| d_arm+25%_trail30 | 12 | 8% | -0.097 | -0.0583 | 0.0583 | — | actual:creator_dump=6, actual:time_stop=3, actual:trailing=1, trailing=2 |
| d_arm+50%_trail30 | 12 | 8% | -0.098 | -0.0585 | 0.0585 | — | actual:creator_dump=7, actual:time_stop=3, actual:trailing=2 |
| d_arm+100%_trail30 | 12 | 8% | -0.098 | -0.0585 | 0.0585 | — | actual:creator_dump=7, actual:time_stop=3, actual:trailing=2 |
| d_arm+25%_trail15 | 12 | 25% | -0.071 | -0.0427 | 0.0546 | — | actual:creator_dump=6, actual:time_stop=3, actual:trailing=1, trailing=2 |
| d_arm+50%_trail15 | 12 | 8% | -0.098 | -0.0585 | 0.0585 | — | actual:creator_dump=7, actual:time_stop=3, actual:trailing=2 |
| d_tp+25%_else_trail30 | 12 | 25% | -0.063 | -0.0378 | 0.0580 | — | actual:creator_dump=5, actual:time_stop=2, actual:trailing=1, target=3, trailing=1 |
| d_tp+50%_else_trail30 | 12 | 8% | -0.092 | -0.0553 | 0.0553 | — | actual:creator_dump=5, actual:time_stop=2, actual:trailing=1, target=1, trailing=3 |
| d_tp+100%_else_trail30 | 12 | 8% | -0.097 | -0.0582 | 0.0582 | — | actual:creator_dump=6, actual:time_stop=2, actual:trailing=1, trailing=3 |
| e_time2m | 12 | 17% | -0.070 | -0.0421 | 0.0538 | — | actual:creator_dump=6, actual:trailing=1, time_stop=5 |
| e_time5m | 12 | 25% | -0.029 | -0.0172 | 0.0473 | — | actual:creator_dump=6, actual:trailing=1, time_stop=5 |
| e_time15m | 12 | 8% | -0.094 | -0.0564 | 0.0564 | — | actual:creator_dump=7, actual:trailing=2, time_stop=3 |
| e_time30m | 12 | 8% | -0.098 | -0.0585 | 0.0585 | — | actual:creator_dump=7, actual:time_stop=3, actual:trailing=2 |
| f_first_creator_sell | 12 | 8% | -0.125 | -0.0748 | 0.0748 | — | actual:creator_dump=3, actual:time_stop=3, actual:trailing=2, creator_sell=4 |
| f2_creator_sell_incl_15s_net_seller | 12 | 8% | -0.121 | -0.0724 | 0.0724 | — | actual:creator_dump=2, actual:time_stop=3, actual:trailing=2, creator_sell=5 |
| g_tp30_or_trail20_or_5m | 12 | 17% | -0.091 | -0.0544 | 0.0544 | — | actual:creator_dump=5, actual:trailing=1, target=2, time_stop=2, trailing=2 |
| g2_tp30_or_trail20_or_2m | 12 | 17% | -0.101 | -0.0609 | 0.0609 | — | actual:creator_dump=5, actual:trailing=1, target=2, time_stop=2, trailing=2 |
| g3_tp50_or_trail20_or_5m | 12 | 17% | -0.064 | -0.0387 | 0.0473 | — | actual:creator_dump=5, actual:trailing=1, target=1, time_stop=3, trailing=2 |
| g4_tp30_or_trail15_or_5m | 12 | 17% | -0.091 | -0.0549 | 0.0549 | — | actual:creator_dump=5, actual:trailing=1, target=2, time_stop=1, trailing=3 |
| g5_tp30_or_trail15_or_2m | 12 | 17% | -0.091 | -0.0548 | 0.0548 | — | actual:creator_dump=5, actual:trailing=1, target=2, time_stop=1, trailing=3 |
| h_tp100_or_trail30_or_5m | 12 | 25% | -0.029 | -0.0172 | 0.0473 | — | actual:creator_dump=6, actual:trailing=1, time_stop=5 |
| h2_tp100_or_trail30_or_15m | 12 | 8% | -0.094 | -0.0562 | 0.0562 | — | actual:creator_dump=6, actual:trailing=1, time_stop=3, trailing=2 |
| h3_tp100_or_trail30_or_30m | 12 | 8% | -0.097 | -0.0582 | 0.0582 | — | actual:creator_dump=6, actual:time_stop=2, actual:trailing=1, trailing=3 |
| h4_tp300_or_trail30_or_30m | 12 | 8% | -0.097 | -0.0582 | 0.0582 | — | actual:creator_dump=6, actual:time_stop=2, actual:trailing=1, trailing=3 |

## operator/5
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 19 | 26% | -0.025 | -0.0240 | 0.0729 | — | creator_dump=9, line_broken=9, time_stop=1 |
| a2_actual_exit_mcap_fee1.25 | 19 | 26% | -0.013 | -0.0123 | 0.0631 | — | creator_dump=9, line_broken=9, time_stop=1 |
| b_line_broken(2) | 19 | 26% | +0.015 | +0.0139 | 0.0416 | 800% | actual:creator_dump=9, actual:line_broken=4, actual:time_stop=1, line_broken=5 |
| b2_paper_full_set | 19 | 26% | +0.023 | +0.0216 | 0.0416 | 528% | actual:creator_dump=5, actual:line_broken=4, actual:time_stop=1, creator_dump=4, line_broken=5 |
| c_trail15 | 19 | 26% | -0.058 | -0.0554 | 0.0698 | — | actual:creator_dump=9, actual:line_broken=4, trailing=6 |
| c_trail30 | 19 | 26% | -0.013 | -0.0122 | 0.0629 | — | actual:creator_dump=9, actual:line_broken=9, trailing=1 |
| c_trail50 | 19 | 26% | -0.013 | -0.0123 | 0.0631 | — | actual:creator_dump=9, actual:line_broken=9, actual:time_stop=1 |
| d_arm+25%_trail30 | 19 | 26% | -0.013 | -0.0123 | 0.0631 | — | actual:creator_dump=9, actual:line_broken=9, actual:time_stop=1 |
| d_arm+50%_trail30 | 19 | 26% | -0.013 | -0.0123 | 0.0631 | — | actual:creator_dump=9, actual:line_broken=9, actual:time_stop=1 |
| d_arm+100%_trail30 | 19 | 26% | -0.013 | -0.0123 | 0.0631 | — | actual:creator_dump=9, actual:line_broken=9, actual:time_stop=1 |
| d_arm+25%_trail15 | 19 | 26% | -0.051 | -0.0487 | 0.0631 | — | actual:creator_dump=9, actual:line_broken=8, actual:time_stop=1, trailing=1 |
| d_arm+50%_trail15 | 19 | 26% | -0.051 | -0.0487 | 0.0631 | — | actual:creator_dump=9, actual:line_broken=8, actual:time_stop=1, trailing=1 |
| d_tp+25%_else_trail30 | 19 | 26% | -0.054 | -0.0513 | 0.0650 | — | actual:creator_dump=8, actual:line_broken=6, target=4, trailing=1 |
| d_tp+50%_else_trail30 | 19 | 26% | -0.016 | -0.0149 | 0.0469 | — | actual:creator_dump=9, actual:line_broken=7, target=2, trailing=1 |
| d_tp+100%_else_trail30 | 19 | 26% | +0.022 | +0.0211 | 0.0411 | 559% | actual:creator_dump=9, actual:line_broken=8, target=1, trailing=1 |
| e_time2m | 19 | 26% | -0.052 | -0.0492 | 0.0666 | — | actual:creator_dump=8, actual:line_broken=5, time_stop=6 |
| e_time5m | 19 | 26% | +0.035 | +0.0330 | 0.0411 | 388% | actual:creator_dump=9, actual:line_broken=8, time_stop=2 |
| e_time15m | 19 | 26% | -0.011 | -0.0105 | 0.0612 | — | actual:creator_dump=9, actual:line_broken=9, time_stop=1 |
| e_time30m | 19 | 26% | -0.013 | -0.0123 | 0.0631 | — | actual:creator_dump=9, actual:line_broken=9, actual:time_stop=1 |
| f_first_creator_sell | 19 | 26% | -0.005 | -0.0047 | 0.0595 | — | actual:creator_dump=5, actual:line_broken=9, actual:time_stop=1, creator_sell=4 |
| f2_creator_sell_incl_15s_net_seller | 19 | 26% | -0.003 | -0.0027 | 0.0575 | — | actual:creator_dump=4, actual:line_broken=9, actual:time_stop=1, creator_sell=5 |
| g_tp30_or_trail20_or_5m | 19 | 26% | -0.040 | -0.0384 | 0.0521 | — | actual:creator_dump=8, actual:line_broken=4, target=4, trailing=3 |
| g2_tp30_or_trail20_or_2m | 19 | 26% | -0.055 | -0.0521 | 0.0658 | — | actual:creator_dump=7, actual:line_broken=3, target=3, time_stop=3, trailing=3 |
| g3_tp50_or_trail20_or_5m | 19 | 26% | -0.014 | -0.0137 | 0.0458 | — | actual:creator_dump=9, actual:line_broken=5, target=2, trailing=3 |
| g4_tp30_or_trail15_or_5m | 19 | 26% | -0.054 | -0.0512 | 0.0649 | — | actual:creator_dump=8, actual:line_broken=3, target=3, trailing=5 |
| g5_tp30_or_trail15_or_2m | 19 | 26% | -0.053 | -0.0506 | 0.0643 | — | actual:creator_dump=7, actual:line_broken=2, target=3, time_stop=2, trailing=5 |
| h_tp100_or_trail30_or_5m | 19 | 26% | +0.024 | +0.0228 | 0.0411 | 517% | actual:creator_dump=9, actual:line_broken=8, target=1, time_stop=1 |
| h2_tp100_or_trail30_or_15m | 19 | 26% | +0.024 | +0.0228 | 0.0411 | 517% | actual:creator_dump=9, actual:line_broken=8, target=1, time_stop=1 |
| h3_tp100_or_trail30_or_30m | 19 | 26% | +0.022 | +0.0211 | 0.0411 | 559% | actual:creator_dump=9, actual:line_broken=8, target=1, trailing=1 |
| h4_tp300_or_trail30_or_30m | 19 | 26% | -0.013 | -0.0122 | 0.0629 | — | actual:creator_dump=9, actual:line_broken=9, trailing=1 |

## flow_v2/5
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 137 | 39% | -0.001 | -0.0082 | 0.2652 | — | creator_dump=41, line_broken=77, max_loss=12, migrated=2, target=1, time_stop=2, trailing=2 |
| a2_actual_exit_mcap_fee1.25 | 137 | 42% | +0.011 | +0.0734 | 0.2562 | 323% | creator_dump=41, line_broken=77, max_loss=12, migrated=2, target=1, time_stop=2, trailing=2 |
| b_line_broken(2) | 137 | 41% | -0.003 | -0.0201 | 0.2533 | — | actual:creator_dump=41, actual:line_broken=51, actual:max_loss=12, actual:migrated=1, actual:target=1, actual:time_stop=2, actual:trailing=2, line_broken=27 |
| b2_paper_full_set | 137 | 40% | -0.007 | -0.0458 | 0.2418 | — | actual:creator_dump=29, actual:line_broken=51, actual:max_loss=5, actual:migrated=1, actual:time_stop=2, actual:trailing=2, creator_dump=12, line_broken=27, max_loss=7, target=1 |
| c_trail15 | 137 | 40% | +0.011 | +0.0781 | 0.1752 | 281% | actual:creator_dump=29, actual:line_broken=54, actual:max_loss=1, actual:migrated=2, actual:target=1, actual:trailing=1, trailing=49 |
| c_trail30 | 137 | 43% | +0.021 | +0.1472 | 0.2342 | 161% | actual:creator_dump=38, actual:line_broken=74, actual:max_loss=1, actual:migrated=2, actual:target=1, actual:time_stop=1, actual:trailing=2, trailing=18 |
| c_trail50 | 137 | 42% | +0.013 | +0.0897 | 0.2447 | 265% | actual:creator_dump=41, actual:line_broken=77, actual:max_loss=4, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, trailing=8 |
| d_arm+25%_trail30 | 137 | 43% | +0.016 | +0.1073 | 0.2562 | 221% | actual:creator_dump=41, actual:line_broken=77, actual:max_loss=10, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, trailing=2 |
| d_arm+50%_trail30 | 137 | 43% | +0.015 | +0.1058 | 0.2562 | 224% | actual:creator_dump=41, actual:line_broken=77, actual:max_loss=11, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, trailing=1 |
| d_arm+100%_trail30 | 137 | 42% | +0.011 | +0.0734 | 0.2562 | 323% | actual:creator_dump=41, actual:line_broken=77, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2 |
| d_arm+25%_trail15 | 137 | 43% | -0.000 | -0.0002 | 0.2163 | — | actual:creator_dump=39, actual:line_broken=71, actual:max_loss=10, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=1, trailing=11 |
| d_arm+50%_trail15 | 137 | 43% | -0.002 | -0.0141 | 0.2311 | — | actual:creator_dump=40, actual:line_broken=73, actual:max_loss=11, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=1, trailing=7 |
| d_tp+25%_else_trail30 | 137 | 47% | -0.010 | -0.0662 | 0.1741 | — | actual:creator_dump=26, actual:line_broken=56, actual:time_stop=1, target=38, trailing=16 |
| d_tp+50%_else_trail30 | 137 | 45% | +0.007 | +0.0454 | 0.1815 | 305% | actual:creator_dump=33, actual:line_broken=63, actual:time_stop=1, target=23, trailing=17 |
| d_tp+100%_else_trail30 | 137 | 44% | +0.038 | +0.2594 | 0.1925 | 84% | actual:creator_dump=38, actual:line_broken=71, actual:migrated=1, actual:time_stop=1, actual:trailing=1, target=7, trailing=18 |
| e_time2m | 137 | 41% | -0.012 | -0.0840 | 0.2444 | — | actual:creator_dump=33, actual:line_broken=59, actual:max_loss=11, actual:migrated=2, actual:trailing=2, time_stop=30 |
| e_time5m | 137 | 42% | +0.006 | +0.0427 | 0.2562 | 523% | actual:creator_dump=40, actual:line_broken=70, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:trailing=2, time_stop=10 |
| e_time15m | 137 | 42% | +0.011 | +0.0750 | 0.2562 | 317% | actual:creator_dump=41, actual:line_broken=77, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:trailing=2, time_stop=2 |
| e_time30m | 137 | 42% | +0.011 | +0.0734 | 0.2562 | 323% | actual:creator_dump=41, actual:line_broken=77, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2 |
| f_first_creator_sell | 137 | 42% | +0.003 | +0.0195 | 0.2608 | 1217% | actual:creator_dump=29, actual:line_broken=77, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, creator_sell=12 |
| f2_creator_sell_incl_15s_net_seller | 137 | 41% | -0.003 | -0.0189 | 0.2429 | — | actual:creator_dump=17, actual:line_broken=75, actual:max_loss=10, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, creator_sell=28 |
| g_tp30_or_trail20_or_5m | 137 | 44% | -0.007 | -0.0467 | 0.1821 | — | actual:creator_dump=22, actual:line_broken=50, target=32, time_stop=4, trailing=29 |
| g2_tp30_or_trail20_or_2m | 137 | 43% | -0.010 | -0.0685 | 0.1726 | — | actual:creator_dump=21, actual:line_broken=48, target=29, time_stop=11, trailing=28 |
| g3_tp50_or_trail20_or_5m | 137 | 42% | +0.004 | +0.0257 | 0.1801 | 538% | actual:creator_dump=28, actual:line_broken=52, target=21, time_stop=5, trailing=31 |
| g4_tp30_or_trail15_or_5m | 137 | 43% | -0.003 | -0.0197 | 0.1703 | — | actual:creator_dump=20, actual:line_broken=45, target=31, time_stop=3, trailing=38 |
| g5_tp30_or_trail15_or_2m | 137 | 42% | -0.004 | -0.0272 | 0.1608 | — | actual:creator_dump=19, actual:line_broken=43, target=29, time_stop=10, trailing=36 |
| h_tp100_or_trail30_or_5m | 137 | 44% | +0.031 | +0.2109 | 0.1925 | 104% | actual:creator_dump=37, actual:line_broken=68, actual:migrated=1, actual:trailing=1, target=5, time_stop=8, trailing=17 |
| h2_tp100_or_trail30_or_15m | 137 | 44% | +0.038 | +0.2594 | 0.1925 | 84% | actual:creator_dump=38, actual:line_broken=71, actual:migrated=1, actual:trailing=1, target=7, time_stop=1, trailing=18 |
| h3_tp100_or_trail30_or_30m | 137 | 44% | +0.038 | +0.2594 | 0.1925 | 84% | actual:creator_dump=38, actual:line_broken=71, actual:migrated=1, actual:time_stop=1, actual:trailing=1, target=7, trailing=18 |
| h4_tp300_or_trail30_or_30m | 137 | 43% | +0.023 | +0.1592 | 0.2342 | 157% | actual:creator_dump=38, actual:line_broken=74, actual:max_loss=1, actual:migrated=2, actual:time_stop=1, actual:trailing=2, target=1, trailing=18 |

## flow_v2/2
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 163 | 40% | +0.009 | +0.0750 | 0.2703 | 378% | creator_dump=53, line_broken=89, max_loss=14, migrated=2, target=1, time_stop=2, trailing=2 |
| a2_actual_exit_mcap_fee1.25 | 163 | 43% | +0.021 | +0.1737 | 0.2562 | 166% | creator_dump=53, line_broken=89, max_loss=14, migrated=2, target=1, time_stop=2, trailing=2 |
| b_line_broken(2) | 163 | 42% | +0.010 | +0.0828 | 0.2483 | 349% | actual:creator_dump=53, actual:line_broken=55, actual:max_loss=14, actual:migrated=1, actual:target=1, actual:time_stop=2, actual:trailing=2, line_broken=35 |
| b2_paper_full_set | 163 | 40% | +0.006 | +0.0521 | 0.2434 | 578% | actual:creator_dump=39, actual:line_broken=55, actual:max_loss=6, actual:migrated=1, actual:time_stop=2, actual:trailing=2, creator_dump=14, line_broken=35, max_loss=8, target=1 |
| c_trail15 | 163 | 41% | +0.031 | +0.2533 | 0.1712 | 112% | actual:creator_dump=37, actual:line_broken=64, actual:max_loss=1, actual:migrated=2, actual:target=1, actual:trailing=1, trailing=57 |
| c_trail30 | 163 | 44% | +0.033 | +0.2716 | 0.2133 | 106% | actual:creator_dump=48, actual:line_broken=85, actual:max_loss=2, actual:migrated=2, actual:target=1, actual:time_stop=1, actual:trailing=2, trailing=22 |
| c_trail50 | 163 | 43% | +0.023 | +0.1899 | 0.2447 | 152% | actual:creator_dump=53, actual:line_broken=89, actual:max_loss=5, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, trailing=9 |
| d_arm+25%_trail30 | 163 | 44% | +0.028 | +0.2293 | 0.2353 | 126% | actual:creator_dump=53, actual:line_broken=89, actual:max_loss=11, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, trailing=3 |
| d_arm+50%_trail30 | 163 | 44% | +0.025 | +0.2060 | 0.2562 | 140% | actual:creator_dump=53, actual:line_broken=89, actual:max_loss=13, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, trailing=1 |
| d_arm+100%_trail30 | 163 | 43% | +0.021 | +0.1737 | 0.2562 | 166% | actual:creator_dump=53, actual:line_broken=89, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2 |
| d_arm+25%_trail15 | 163 | 44% | +0.016 | +0.1302 | 0.1954 | 218% | actual:creator_dump=51, actual:line_broken=83, actual:max_loss=11, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=1, trailing=12 |
| d_arm+50%_trail15 | 163 | 44% | +0.011 | +0.0861 | 0.2311 | 329% | actual:creator_dump=52, actual:line_broken=85, actual:max_loss=13, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=1, trailing=7 |
| d_tp+25%_else_trail30 | 163 | 48% | +0.010 | +0.0840 | 0.1597 | 241% | actual:creator_dump=34, actual:line_broken=65, actual:max_loss=1, actual:time_stop=1, target=43, trailing=19 |
| d_tp+50%_else_trail30 | 163 | 45% | +0.023 | +0.1910 | 0.1888 | 111% | actual:creator_dump=41, actual:line_broken=73, actual:max_loss=1, actual:time_stop=1, target=26, trailing=21 |
| d_tp+100%_else_trail30 | 163 | 44% | +0.047 | +0.3837 | 0.1716 | 73% | actual:creator_dump=48, actual:line_broken=82, actual:max_loss=1, actual:migrated=1, actual:time_stop=1, actual:trailing=1, target=7, trailing=22 |
| e_time2m | 163 | 42% | +0.002 | +0.0144 | 0.2692 | 1962% | actual:creator_dump=43, actual:line_broken=68, actual:max_loss=13, actual:migrated=2, actual:trailing=2, time_stop=35 |
| e_time5m | 163 | 43% | +0.020 | +0.1604 | 0.2494 | 177% | actual:creator_dump=51, actual:line_broken=81, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:trailing=2, time_stop=12 |
| e_time15m | 163 | 43% | +0.022 | +0.1752 | 0.2562 | 165% | actual:creator_dump=53, actual:line_broken=89, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:trailing=2, time_stop=2 |
| e_time30m | 163 | 43% | +0.021 | +0.1737 | 0.2562 | 166% | actual:creator_dump=53, actual:line_broken=89, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2 |
| f_first_creator_sell | 163 | 42% | +0.014 | +0.1147 | 0.2628 | 252% | actual:creator_dump=39, actual:line_broken=89, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, creator_sell=14 |
| f2_creator_sell_incl_15s_net_seller | 163 | 42% | +0.011 | +0.0927 | 0.2449 | 312% | actual:creator_dump=22, actual:line_broken=85, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:time_stop=2, actual:trailing=2, creator_sell=37 |
| g_tp30_or_trail20_or_5m | 163 | 44% | +0.014 | +0.1151 | 0.1438 | 176% | actual:creator_dump=29, actual:line_broken=59, target=36, time_stop=5, trailing=34 |
| g2_tp30_or_trail20_or_2m | 163 | 44% | +0.008 | +0.0690 | 0.1613 | 293% | actual:creator_dump=28, actual:line_broken=56, target=33, time_stop=13, trailing=33 |
| g3_tp50_or_trail20_or_5m | 163 | 42% | +0.025 | +0.2078 | 0.1676 | 102% | actual:creator_dump=35, actual:line_broken=62, target=24, time_stop=6, trailing=36 |
| g4_tp30_or_trail15_or_5m | 163 | 44% | +0.019 | +0.1564 | 0.1295 | 129% | actual:creator_dump=26, actual:line_broken=53, target=35, time_stop=3, trailing=46 |
| g5_tp30_or_trail15_or_2m | 163 | 43% | +0.015 | +0.1228 | 0.1532 | 165% | actual:creator_dump=25, actual:line_broken=50, target=33, time_stop=11, trailing=44 |
| h_tp100_or_trail30_or_5m | 163 | 44% | +0.043 | +0.3510 | 0.1716 | 80% | actual:creator_dump=47, actual:line_broken=78, actual:max_loss=1, actual:migrated=1, actual:trailing=1, target=5, time_stop=10, trailing=20 |
| h2_tp100_or_trail30_or_15m | 163 | 44% | +0.047 | +0.3837 | 0.1716 | 73% | actual:creator_dump=48, actual:line_broken=82, actual:max_loss=1, actual:migrated=1, actual:trailing=1, target=7, time_stop=1, trailing=22 |
| h3_tp100_or_trail30_or_30m | 163 | 44% | +0.047 | +0.3837 | 0.1716 | 73% | actual:creator_dump=48, actual:line_broken=82, actual:max_loss=1, actual:migrated=1, actual:time_stop=1, actual:trailing=1, target=7, trailing=22 |
| h4_tp300_or_trail30_or_30m | 163 | 44% | +0.035 | +0.2836 | 0.2133 | 106% | actual:creator_dump=48, actual:line_broken=85, actual:max_loss=2, actual:migrated=2, actual:time_stop=1, actual:trailing=2, target=1, trailing=22 |

## flow_v2/6
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 25 | 16% | +0.007 | +0.0087 | 0.0942 | 1626% | creator_dump=7, line_broken=15, time_stop=3 |
| a2_actual_exit_mcap_fee1.25 | 25 | 24% | +0.020 | +0.0246 | 0.0865 | 589% | creator_dump=7, line_broken=15, time_stop=3 |
| b_line_broken(2) | 25 | 24% | +0.025 | +0.0318 | 0.0857 | 433% | actual:creator_dump=7, actual:line_broken=6, actual:time_stop=3, line_broken=9 |
| b2_paper_full_set | 25 | 24% | +0.026 | +0.0319 | 0.0856 | 433% | actual:creator_dump=4, actual:line_broken=6, actual:time_stop=3, creator_dump=3, line_broken=9 |
| c_trail15 | 25 | 28% | +0.062 | +0.0772 | 0.0564 | 188% | actual:creator_dump=6, actual:line_broken=12, trailing=7 |
| c_trail30 | 25 | 28% | +0.041 | +0.0507 | 0.0676 | 286% | actual:creator_dump=6, actual:line_broken=14, actual:time_stop=1, trailing=4 |
| c_trail50 | 25 | 24% | +0.020 | +0.0255 | 0.0857 | 569% | actual:creator_dump=7, actual:line_broken=14, actual:time_stop=3, trailing=1 |
| d_arm+25%_trail30 | 25 | 28% | +0.039 | +0.0485 | 0.0697 | 298% | actual:creator_dump=7, actual:line_broken=14, actual:time_stop=3, trailing=1 |
| d_arm+50%_trail30 | 25 | 28% | +0.039 | +0.0485 | 0.0697 | 298% | actual:creator_dump=7, actual:line_broken=14, actual:time_stop=3, trailing=1 |
| d_arm+100%_trail30 | 25 | 24% | +0.020 | +0.0246 | 0.0865 | 589% | actual:creator_dump=7, actual:line_broken=15, actual:time_stop=3 |
| d_arm+25%_trail15 | 25 | 28% | +0.039 | +0.0485 | 0.0697 | 298% | actual:creator_dump=7, actual:line_broken=14, actual:time_stop=3, trailing=1 |
| d_arm+50%_trail15 | 25 | 28% | +0.039 | +0.0485 | 0.0697 | 298% | actual:creator_dump=7, actual:line_broken=14, actual:time_stop=3, trailing=1 |
| d_tp+25%_else_trail30 | 25 | 28% | -0.012 | -0.0150 | 0.0564 | — | actual:creator_dump=4, actual:line_broken=11, actual:time_stop=1, target=6, trailing=3 |
| d_tp+50%_else_trail30 | 25 | 28% | +0.010 | +0.0129 | 0.0676 | 701% | actual:creator_dump=5, actual:line_broken=12, actual:time_stop=1, target=4, trailing=3 |
| d_tp+100%_else_trail30 | 25 | 28% | +0.046 | +0.0575 | 0.0676 | 264% | actual:creator_dump=6, actual:line_broken=13, actual:time_stop=1, target=1, trailing=4 |
| e_time2m | 25 | 24% | -0.017 | -0.0218 | 0.0826 | — | actual:creator_dump=7, actual:line_broken=10, time_stop=8 |
| e_time5m | 25 | 24% | +0.011 | +0.0134 | 0.0843 | 979% | actual:creator_dump=7, actual:line_broken=14, time_stop=4 |
| e_time15m | 25 | 24% | +0.021 | +0.0265 | 0.0847 | 546% | actual:creator_dump=7, actual:line_broken=15, time_stop=3 |
| e_time30m | 25 | 24% | +0.020 | +0.0246 | 0.0865 | 589% | actual:creator_dump=7, actual:line_broken=15, actual:time_stop=3 |
| f_first_creator_sell | 25 | 24% | +0.020 | +0.0246 | 0.0865 | 588% | actual:creator_dump=4, actual:line_broken=15, actual:time_stop=3, creator_sell=3 |
| f2_creator_sell_incl_15s_net_seller | 25 | 28% | -0.005 | -0.0057 | 0.0842 | — | actual:creator_dump=2, actual:line_broken=15, actual:time_stop=3, creator_sell=5 |
| g_tp30_or_trail20_or_5m | 25 | 28% | -0.003 | -0.0032 | 0.0576 | — | actual:creator_dump=5, actual:line_broken=11, target=5, trailing=4 |
| g2_tp30_or_trail20_or_2m | 25 | 28% | -0.008 | -0.0102 | 0.0574 | — | actual:creator_dump=5, actual:line_broken=9, target=4, time_stop=3, trailing=4 |
| g3_tp50_or_trail20_or_5m | 25 | 28% | +0.020 | +0.0256 | 0.0576 | 353% | actual:creator_dump=5, actual:line_broken=12, target=4, trailing=4 |
| g4_tp30_or_trail15_or_5m | 25 | 28% | +0.008 | +0.0106 | 0.0564 | 681% | actual:creator_dump=5, actual:line_broken=9, target=5, trailing=6 |
| g5_tp30_or_trail15_or_2m | 25 | 28% | +0.003 | +0.0036 | 0.0562 | 1995% | actual:creator_dump=5, actual:line_broken=7, target=4, time_stop=3, trailing=6 |
| h_tp100_or_trail30_or_5m | 25 | 28% | +0.031 | +0.0393 | 0.0655 | 334% | actual:creator_dump=6, actual:line_broken=13, time_stop=3, trailing=3 |
| h2_tp100_or_trail30_or_15m | 25 | 28% | +0.047 | +0.0592 | 0.0659 | 256% | actual:creator_dump=6, actual:line_broken=13, target=1, time_stop=2, trailing=3 |
| h3_tp100_or_trail30_or_30m | 25 | 28% | +0.046 | +0.0575 | 0.0676 | 264% | actual:creator_dump=6, actual:line_broken=13, actual:time_stop=1, target=1, trailing=4 |
| h4_tp300_or_trail30_or_30m | 25 | 28% | +0.041 | +0.0507 | 0.0676 | 286% | actual:creator_dump=6, actual:line_broken=14, actual:time_stop=1, trailing=4 |

## flow_v2/8
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 31 | 29% | +0.003 | +0.0039 | 0.0891 | 3745% | creator_dump=8, line_broken=19, max_loss=1, time_stop=3 |
| a2_actual_exit_mcap_fee1.25 | 31 | 32% | +0.015 | +0.0234 | 0.0834 | 640% | creator_dump=8, line_broken=19, max_loss=1, time_stop=3 |
| b_line_broken(2) | 31 | 32% | +0.019 | +0.0293 | 0.0714 | 478% | actual:creator_dump=8, actual:line_broken=5, actual:max_loss=1, actual:time_stop=3, line_broken=14 |
| b2_paper_full_set | 31 | 35% | +0.023 | +0.0356 | 0.0651 | 394% | actual:creator_dump=5, actual:line_broken=5, actual:time_stop=3, creator_dump=3, line_broken=14, max_loss=1 |
| c_trail15 | 31 | 35% | +0.067 | +0.1034 | 0.0670 | 145% | actual:creator_dump=8, actual:line_broken=15, trailing=8 |
| c_trail30 | 31 | 32% | +0.027 | +0.0413 | 0.0823 | 363% | actual:creator_dump=8, actual:line_broken=17, actual:time_stop=2, trailing=4 |
| c_trail50 | 31 | 32% | +0.017 | +0.0266 | 0.0834 | 562% | actual:creator_dump=8, actual:line_broken=19, actual:time_stop=3, trailing=1 |
| d_arm+25%_trail30 | 31 | 32% | +0.015 | +0.0234 | 0.0834 | 640% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=3 |
| d_arm+50%_trail30 | 31 | 32% | +0.015 | +0.0234 | 0.0834 | 640% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=3 |
| d_arm+100%_trail30 | 31 | 32% | +0.015 | +0.0234 | 0.0834 | 640% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=3 |
| d_arm+25%_trail15 | 31 | 35% | +0.041 | +0.0639 | 0.0834 | 234% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=2, trailing=1 |
| d_arm+50%_trail15 | 31 | 35% | +0.041 | +0.0639 | 0.0834 | 234% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=2, trailing=1 |
| d_tp+25%_else_trail30 | 31 | 35% | +0.018 | +0.0283 | 0.0823 | 378% | actual:creator_dump=6, actual:line_broken=12, actual:time_stop=1, target=8, trailing=4 |
| d_tp+50%_else_trail30 | 31 | 35% | +0.029 | +0.0453 | 0.0823 | 235% | actual:creator_dump=7, actual:line_broken=14, actual:time_stop=1, target=5, trailing=4 |
| d_tp+100%_else_trail30 | 31 | 32% | +0.031 | +0.0481 | 0.0823 | 325% | actual:creator_dump=8, actual:line_broken=16, actual:time_stop=2, target=1, trailing=4 |
| e_time2m | 31 | 32% | -0.023 | -0.0359 | 0.0806 | — | actual:creator_dump=8, actual:line_broken=15, actual:max_loss=1, actual:time_stop=1, time_stop=6 |
| e_time5m | 31 | 32% | +0.007 | +0.0103 | 0.0833 | 1326% | actual:creator_dump=8, actual:line_broken=18, actual:max_loss=1, actual:time_stop=1, time_stop=3 |
| e_time15m | 31 | 32% | +0.015 | +0.0234 | 0.0833 | 639% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=1, time_stop=2 |
| e_time30m | 31 | 32% | +0.015 | +0.0234 | 0.0834 | 640% | actual:creator_dump=8, actual:line_broken=19, actual:max_loss=1, actual:time_stop=3 |
| f_first_creator_sell | 31 | 35% | +0.017 | +0.0264 | 0.0834 | 567% | actual:creator_dump=5, actual:line_broken=19, actual:max_loss=1, actual:time_stop=3, creator_sell=3 |
| f2_creator_sell_incl_15s_net_seller | 31 | 35% | -0.007 | -0.0116 | 0.0903 | — | actual:creator_dump=1, actual:line_broken=19, actual:max_loss=1, actual:time_stop=3, creator_sell=7 |
| g_tp30_or_trail20_or_5m | 31 | 35% | +0.021 | +0.0327 | 0.0796 | 327% | actual:creator_dump=7, actual:line_broken=11, target=7, trailing=6 |
| g2_tp30_or_trail20_or_2m | 31 | 35% | +0.016 | +0.0255 | 0.0796 | 418% | actual:creator_dump=7, actual:line_broken=10, target=6, time_stop=2, trailing=6 |
| g3_tp50_or_trail20_or_5m | 31 | 35% | +0.035 | +0.0543 | 0.0796 | 196% | actual:creator_dump=7, actual:line_broken=13, target=5, trailing=6 |
| g4_tp30_or_trail15_or_5m | 31 | 35% | +0.029 | +0.0453 | 0.0670 | 236% | actual:creator_dump=7, actual:line_broken=10, target=7, trailing=7 |
| g5_tp30_or_trail15_or_2m | 31 | 35% | +0.025 | +0.0382 | 0.0670 | 280% | actual:creator_dump=7, actual:line_broken=9, target=6, time_stop=2, trailing=7 |
| h_tp100_or_trail30_or_5m | 31 | 32% | +0.018 | +0.0282 | 0.0823 | 487% | actual:creator_dump=8, actual:line_broken=16, actual:time_stop=1, time_stop=2, trailing=4 |
| h2_tp100_or_trail30_or_15m | 31 | 32% | +0.031 | +0.0481 | 0.0823 | 325% | actual:creator_dump=8, actual:line_broken=16, actual:time_stop=1, target=1, time_stop=1, trailing=4 |
| h3_tp100_or_trail30_or_30m | 31 | 32% | +0.031 | +0.0481 | 0.0823 | 325% | actual:creator_dump=8, actual:line_broken=16, actual:time_stop=2, target=1, trailing=4 |
| h4_tp300_or_trail30_or_30m | 31 | 32% | +0.027 | +0.0413 | 0.0823 | 363% | actual:creator_dump=8, actual:line_broken=17, actual:time_stop=2, trailing=4 |

## papel (5 sets)
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 375 | 37% | +0.003 | +0.0554 | 0.5636 | 557% | creator_dump=118, line_broken=209, max_loss=27, migrated=4, target=2, time_stop=11, trailing=4 |
| a2_actual_exit_mcap_fee1.25 | 375 | 40% | +0.015 | +0.2827 | 0.5327 | 111% | creator_dump=118, line_broken=209, max_loss=27, migrated=4, target=2, time_stop=11, trailing=4 |
| b_line_broken(2) | 375 | 39% | +0.007 | +0.1378 | 0.5151 | 228% | actual:creator_dump=118, actual:line_broken=121, actual:max_loss=27, actual:migrated=2, actual:target=2, actual:time_stop=11, actual:trailing=4, line_broken=90 |
| b2_paper_full_set | 375 | 38% | +0.005 | +0.0953 | 0.5050 | 355% | actual:creator_dump=82, actual:line_broken=121, actual:max_loss=11, actual:migrated=2, actual:time_stop=11, actual:trailing=4, creator_dump=36, line_broken=90, max_loss=16, target=2 |
| c_trail15 | 375 | 39% | +0.024 | +0.4566 | 0.3696 | 69% | actual:creator_dump=89, actual:line_broken=149, actual:max_loss=2, actual:migrated=4, actual:target=2, actual:trailing=2, trailing=127 |
| c_trail30 | 375 | 41% | +0.027 | +0.4986 | 0.4444 | 63% | actual:creator_dump=109, actual:line_broken=199, actual:max_loss=3, actual:migrated=4, actual:target=2, actual:time_stop=5, actual:trailing=4, trailing=49 |
| c_trail50 | 375 | 40% | +0.017 | +0.3194 | 0.5088 | 98% | actual:creator_dump=118, actual:line_broken=208, actual:max_loss=9, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4, trailing=19 |
| d_arm+25%_trail30 | 375 | 41% | +0.021 | +0.3961 | 0.4885 | 79% | actual:creator_dump=118, actual:line_broken=208, actual:max_loss=22, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4, trailing=6 |
| d_arm+50%_trail30 | 375 | 41% | +0.020 | +0.3714 | 0.5087 | 85% | actual:creator_dump=118, actual:line_broken=208, actual:max_loss=25, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4, trailing=3 |
| d_arm+100%_trail30 | 375 | 40% | +0.015 | +0.2827 | 0.5327 | 111% | actual:creator_dump=118, actual:line_broken=209, actual:max_loss=27, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4 |
| d_arm+25%_trail15 | 375 | 41% | +0.010 | +0.1938 | 0.4086 | 162% | actual:creator_dump=114, actual:line_broken=195, actual:max_loss=22, actual:migrated=4, actual:target=2, actual:time_stop=10, actual:trailing=2, trailing=26 |
| d_arm+50%_trail15 | 375 | 41% | +0.007 | +0.1358 | 0.4585 | 231% | actual:creator_dump=116, actual:line_broken=199, actual:max_loss=25, actual:migrated=4, actual:target=2, actual:time_stop=10, actual:trailing=2, trailing=17 |
| d_tp+25%_else_trail30 | 375 | 44% | -0.001 | -0.0202 | 0.3579 | — | actual:creator_dump=78, actual:line_broken=150, actual:max_loss=1, actual:time_stop=4, target=99, trailing=43 |
| d_tp+50%_else_trail30 | 375 | 42% | +0.015 | +0.2798 | 0.3537 | 76% | actual:creator_dump=95, actual:line_broken=169, actual:max_loss=1, actual:time_stop=4, target=60, trailing=46 |
| d_tp+100%_else_trail30 | 375 | 41% | +0.041 | +0.7697 | 0.3609 | 40% | actual:creator_dump=109, actual:line_broken=190, actual:max_loss=1, actual:migrated=2, actual:time_stop=5, actual:trailing=2, target=17, trailing=49 |
| e_time2m | 375 | 39% | -0.009 | -0.1766 | 0.5544 | — | actual:creator_dump=99, actual:line_broken=157, actual:max_loss=25, actual:migrated=4, actual:time_stop=1, actual:trailing=4, time_stop=85 |
| e_time5m | 375 | 40% | +0.014 | +0.2598 | 0.5414 | 121% | actual:creator_dump=115, actual:line_broken=191, actual:max_loss=27, actual:migrated=4, actual:target=2, actual:time_stop=1, actual:trailing=4, time_stop=31 |
| e_time15m | 375 | 40% | +0.015 | +0.2897 | 0.5327 | 109% | actual:creator_dump=118, actual:line_broken=209, actual:max_loss=27, actual:migrated=4, actual:target=2, actual:time_stop=1, actual:trailing=4, time_stop=10 |
| e_time30m | 375 | 40% | +0.015 | +0.2827 | 0.5327 | 111% | actual:creator_dump=118, actual:line_broken=209, actual:max_loss=27, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4 |
| f_first_creator_sell | 375 | 39% | +0.010 | +0.1805 | 0.5455 | 174% | actual:creator_dump=82, actual:line_broken=209, actual:max_loss=27, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4, creator_sell=36 |
| f2_creator_sell_incl_15s_net_seller | 375 | 39% | +0.003 | +0.0538 | 0.5106 | 584% | actual:creator_dump=46, actual:line_broken=203, actual:max_loss=23, actual:migrated=4, actual:target=2, actual:time_stop=11, actual:trailing=4, creator_sell=82 |
| g_tp30_or_trail20_or_5m | 375 | 41% | +0.003 | +0.0595 | 0.3519 | 359% | actual:creator_dump=71, actual:line_broken=135, target=84, time_stop=9, trailing=76 |
| g2_tp30_or_trail20_or_2m | 375 | 41% | -0.002 | -0.0362 | 0.3641 | — | actual:creator_dump=68, actual:line_broken=126, target=75, time_stop=32, trailing=74 |
| g3_tp50_or_trail20_or_5m | 375 | 40% | +0.016 | +0.2998 | 0.3433 | 71% | actual:creator_dump=84, actual:line_broken=144, target=56, time_stop=11, trailing=80 |
| g4_tp30_or_trail15_or_5m | 375 | 41% | +0.008 | +0.1415 | 0.3192 | 151% | actual:creator_dump=66, actual:line_broken=120, target=81, time_stop=6, trailing=102 |
| g5_tp30_or_trail15_or_2m | 375 | 40% | +0.005 | +0.0868 | 0.3314 | 246% | actual:creator_dump=63, actual:line_broken=111, target=75, time_stop=28, trailing=98 |
| h_tp100_or_trail30_or_5m | 375 | 41% | +0.035 | +0.6521 | 0.3718 | 48% | actual:creator_dump=107, actual:line_broken=183, actual:max_loss=1, actual:migrated=2, actual:time_stop=1, actual:trailing=2, target=11, time_stop=24, trailing=44 |
| h2_tp100_or_trail30_or_15m | 375 | 41% | +0.041 | +0.7732 | 0.3609 | 40% | actual:creator_dump=109, actual:line_broken=190, actual:max_loss=1, actual:migrated=2, actual:time_stop=1, actual:trailing=2, target=17, time_stop=6, trailing=47 |
| h3_tp100_or_trail30_or_30m | 375 | 41% | +0.041 | +0.7697 | 0.3609 | 40% | actual:creator_dump=109, actual:line_broken=190, actual:max_loss=1, actual:migrated=2, actual:time_stop=5, actual:trailing=2, target=17, trailing=49 |
| h4_tp300_or_trail30_or_30m | 375 | 41% | +0.028 | +0.5226 | 0.4444 | 65% | actual:creator_dump=109, actual:line_broken=199, actual:max_loss=3, actual:migrated=4, actual:time_stop=5, actual:trailing=4, target=2, trailing=49 |

## papel unico (mint@minuto)
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 215 | 36% | -0.002 | -0.0188 | 0.3069 | — | creator_dump=71, line_broken=118, max_loss=15, migrated=2, target=1, time_stop=6, trailing=2 |
| a2_actual_exit_mcap_fee1.25 | 215 | 39% | +0.010 | +0.1115 | 0.2895 | 259% | creator_dump=71, line_broken=118, max_loss=15, migrated=2, target=1, time_stop=6, trailing=2 |
| b_line_broken(2) | 215 | 38% | +0.003 | +0.0273 | 0.2809 | 1060% | actual:creator_dump=71, actual:line_broken=66, actual:max_loss=15, actual:migrated=1, actual:target=1, actual:time_stop=6, actual:trailing=2, line_broken=53 |
| b2_paper_full_set | 215 | 38% | +0.001 | +0.0105 | 0.2757 | 2868% | actual:creator_dump=48, actual:line_broken=66, actual:max_loss=6, actual:migrated=1, actual:time_stop=6, actual:trailing=2, creator_dump=23, line_broken=53, max_loss=9, target=1 |
| c_trail15 | 215 | 39% | +0.029 | +0.3113 | 0.1913 | 92% | actual:creator_dump=54, actual:line_broken=85, actual:max_loss=1, actual:migrated=2, actual:target=1, actual:trailing=1, trailing=71 |
| c_trail30 | 215 | 40% | +0.024 | +0.2533 | 0.2179 | 114% | actual:creator_dump=65, actual:line_broken=111, actual:max_loss=2, actual:migrated=2, actual:target=1, actual:time_stop=3, actual:trailing=2, trailing=29 |
| c_trail50 | 215 | 39% | +0.012 | +0.1319 | 0.2772 | 219% | actual:creator_dump=71, actual:line_broken=117, actual:max_loss=5, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2, trailing=11 |
| d_arm+25%_trail30 | 215 | 40% | +0.018 | +0.1910 | 0.2439 | 151% | actual:creator_dump=71, actual:line_broken=117, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2, trailing=4 |
| d_arm+50%_trail30 | 215 | 40% | +0.016 | +0.1678 | 0.2656 | 172% | actual:creator_dump=71, actual:line_broken=117, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2, trailing=2 |
| d_arm+100%_trail30 | 215 | 39% | +0.010 | +0.1115 | 0.2895 | 259% | actual:creator_dump=71, actual:line_broken=118, actual:max_loss=15, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2 |
| d_arm+25%_trail15 | 215 | 40% | +0.012 | +0.1325 | 0.2154 | 216% | actual:creator_dump=69, actual:line_broken=111, actual:max_loss=12, actual:migrated=2, actual:target=1, actual:time_stop=5, actual:trailing=1, trailing=14 |
| d_arm+50%_trail15 | 215 | 40% | +0.008 | +0.0884 | 0.2405 | 323% | actual:creator_dump=70, actual:line_broken=113, actual:max_loss=14, actual:migrated=2, actual:target=1, actual:time_stop=5, actual:trailing=1, trailing=9 |
| d_tp+25%_else_trail30 | 215 | 44% | +0.006 | +0.0605 | 0.1813 | 339% | actual:creator_dump=48, actual:line_broken=85, actual:max_loss=1, actual:time_stop=2, target=54, trailing=25 |
| d_tp+50%_else_trail30 | 215 | 41% | +0.018 | +0.1934 | 0.1955 | 110% | actual:creator_dump=57, actual:line_broken=96, actual:max_loss=1, actual:time_stop=2, target=32, trailing=27 |
| d_tp+100%_else_trail30 | 215 | 40% | +0.035 | +0.3722 | 0.1783 | 76% | actual:creator_dump=65, actual:line_broken=107, actual:max_loss=1, actual:migrated=1, actual:time_stop=3, actual:trailing=1, target=8, trailing=29 |
| e_time2m | 215 | 38% | -0.009 | -0.1001 | 0.3226 | — | actual:creator_dump=60, actual:line_broken=90, actual:max_loss=14, actual:migrated=2, actual:time_stop=1, actual:trailing=2, time_stop=46 |
| e_time5m | 215 | 39% | +0.008 | +0.0870 | 0.3020 | 329% | actual:creator_dump=69, actual:line_broken=109, actual:max_loss=15, actual:migrated=2, actual:target=1, actual:time_stop=1, actual:trailing=2, time_stop=16 |
| e_time15m | 215 | 39% | +0.011 | +0.1149 | 0.2895 | 252% | actual:creator_dump=71, actual:line_broken=118, actual:max_loss=15, actual:migrated=2, actual:target=1, actual:time_stop=1, actual:trailing=2, time_stop=5 |
| e_time30m | 215 | 39% | +0.010 | +0.1115 | 0.2895 | 259% | actual:creator_dump=71, actual:line_broken=118, actual:max_loss=15, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2 |
| f_first_creator_sell | 215 | 39% | +0.006 | +0.0632 | 0.2958 | 458% | actual:creator_dump=48, actual:line_broken=118, actual:max_loss=15, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2, creator_sell=23 |
| f2_creator_sell_incl_15s_net_seller | 215 | 39% | +0.001 | +0.0071 | 0.2779 | 4081% | actual:creator_dump=27, actual:line_broken=114, actual:max_loss=13, actual:migrated=2, actual:target=1, actual:time_stop=6, actual:trailing=2, creator_sell=50 |
| g_tp30_or_trail20_or_5m | 215 | 41% | +0.011 | +0.1170 | 0.1666 | 175% | actual:creator_dump=44, actual:line_broken=77, target=46, time_stop=5, trailing=43 |
| g2_tp30_or_trail20_or_2m | 215 | 40% | +0.006 | +0.0644 | 0.1856 | 318% | actual:creator_dump=42, actual:line_broken=72, target=42, time_stop=17, trailing=42 |
| g3_tp50_or_trail20_or_5m | 215 | 40% | +0.021 | +0.2271 | 0.1823 | 94% | actual:creator_dump=51, actual:line_broken=83, target=30, time_stop=6, trailing=45 |
| g4_tp30_or_trail15_or_5m | 215 | 40% | +0.016 | +0.1772 | 0.1485 | 116% | actual:creator_dump=41, actual:line_broken=68, target=45, time_stop=3, trailing=58 |
| g5_tp30_or_trail15_or_2m | 215 | 40% | +0.013 | +0.1372 | 0.1675 | 149% | actual:creator_dump=39, actual:line_broken=63, target=42, time_stop=15, trailing=56 |
| h_tp100_or_trail30_or_5m | 215 | 40% | +0.030 | +0.3213 | 0.1954 | 88% | actual:creator_dump=64, actual:line_broken=103, actual:max_loss=1, actual:migrated=1, actual:time_stop=1, actual:trailing=1, target=5, time_stop=13, trailing=26 |
| h2_tp100_or_trail30_or_15m | 215 | 40% | +0.035 | +0.3739 | 0.1783 | 76% | actual:creator_dump=65, actual:line_broken=107, actual:max_loss=1, actual:migrated=1, actual:time_stop=1, actual:trailing=1, target=8, time_stop=3, trailing=28 |
| h3_tp100_or_trail30_or_30m | 215 | 40% | +0.035 | +0.3722 | 0.1783 | 76% | actual:creator_dump=65, actual:line_broken=107, actual:max_loss=1, actual:migrated=1, actual:time_stop=3, actual:trailing=1, target=8, trailing=29 |
| h4_tp300_or_trail30_or_30m | 215 | 40% | +0.025 | +0.2653 | 0.2179 | 114% | actual:creator_dump=65, actual:line_broken=111, actual:max_loss=2, actual:migrated=2, actual:time_stop=3, actual:trailing=2, target=1, trailing=29 |

## as posicoes reais, aposta a aposta (PnL a 0,05 SOL, taxas 1,25 %)
| mint | cobertura | a_actual_recorded | b_line_broken(2) | c_trail15 | c_trail30 | e_time2m | e_time5m | f_first_creator_sell | g_tp30_or_trail20_or_5m | g5_tp30_or_trail15_or_2m |
|---|---|---|---|---|---|---|---|---|---|---|
| 7s4dKmpv | 39s | -0.0093 (creator_dump, 48s) | -0.0070 (actual:creator_dump, 48s) | -0.0070 (actual:creator_dump, 48s) | -0.0070 (actual:creator_dump, 48s) | -0.0070 (actual:creator_dump, 48s) | -0.0070 (actual:creator_dump, 48s) | -0.0070 (actual:creator_dump, 48s) | -0.0070 (actual:creator_dump, 48s) | -0.0070 (actual:creator_dump, 48s) |
| 63NPcW9q | 46s | -0.0035 (creator_dump, 52s) | -0.0012 (line_broken, 31s) | -0.0022 (actual:creator_dump, 52s) | -0.0022 (actual:creator_dump, 52s) | -0.0022 (actual:creator_dump, 52s) | -0.0022 (actual:creator_dump, 52s) | -0.0021 (creator_sell, 46s) | -0.0022 (actual:creator_dump, 52s) | -0.0022 (actual:creator_dump, 52s) |
| CCLstvwa | 394s | -0.0071 (trailing, 396s) | -0.0117 (line_broken, 56s) | -0.0101 (trailing, 24s) | -0.0058 (trailing, 394s) | -0.0115 (time_stop, 121s) | +0.0143 (time_stop, 314s) | -0.0060 (actual:trailing, 396s) | -0.0117 (trailing, 40s) | -0.0101 (trailing, 24s) |
| 2hhJXPy3 | 1557s | -0.0176 (time_stop, 1800s) | -0.0167 (actual:time_stop, 1800s) | -0.0104 (trailing, 20s) | -0.0165 (trailing, 1366s) | -0.0148 (time_stop, 132s) | -0.0148 (time_stop, 307s) | -0.0167 (actual:time_stop, 1800s) | -0.0131 (trailing, 52s) | -0.0104 (trailing, 20s) |
| Dy9YAbcL | 514s | -0.0059 (creator_dump, 514s) | +0.0122 (line_broken, 204s) | +0.0030 (trailing, 338s) | -0.0046 (trailing, 449s) | +0.0146 (time_stop, 124s) | +0.0072 (time_stop, 306s) | -0.0048 (creator_sell, 465s) | +0.0139 (target, 93s) | +0.0139 (target, 93s) |
| GdZ5hSdz | 80s | -0.0038 (creator_dump, 86s) | -0.0025 (actual:creator_dump, 86s) | -0.0025 (actual:creator_dump, 86s) | -0.0025 (actual:creator_dump, 86s) | -0.0025 (actual:creator_dump, 86s) | -0.0025 (actual:creator_dump, 86s) | -0.0025 (actual:creator_dump, 86s) | -0.0025 (actual:creator_dump, 86s) | -0.0025 (actual:creator_dump, 86s) |
| 6zdT1MxC | 104s | +0.0329 (creator_dump, 117s) | +0.0352 (actual:creator_dump, 117s) | +0.0352 (actual:creator_dump, 117s) | +0.0352 (actual:creator_dump, 117s) | +0.0352 (actual:creator_dump, 117s) | +0.0352 (actual:creator_dump, 117s) | +0.0186 (creator_sell, 55s) | +0.0157 (target, 39s) | +0.0157 (target, 39s) |
| rYJYP8jV | 42s | -0.0040 (creator_dump, 45s) | -0.0028 (actual:creator_dump, 45s) | -0.0028 (actual:creator_dump, 45s) | -0.0028 (actual:creator_dump, 45s) | -0.0028 (actual:creator_dump, 45s) | -0.0028 (actual:creator_dump, 45s) | -0.0026 (creator_sell, 42s) | -0.0028 (actual:creator_dump, 45s) | -0.0028 (actual:creator_dump, 45s) |
| M3kpWCVA | 1586s | -0.0122 (time_stop, 1804s) | -0.0074 (line_broken, 31s) | -0.0089 (trailing, 63s) | -0.0111 (actual:time_stop, 1804s) | -0.0105 (time_stop, 129s) | -0.0040 (time_stop, 308s) | -0.0111 (actual:time_stop, 1804s) | -0.0040 (time_stop, 308s) | -0.0089 (trailing, 63s) |
| 8DqtPVgJ | 28s | -0.0025 (creator_dump, 33s) | -0.0012 (actual:creator_dump, 33s) | -0.0012 (actual:creator_dump, 33s) | -0.0012 (actual:creator_dump, 33s) | -0.0012 (actual:creator_dump, 33s) | -0.0012 (actual:creator_dump, 33s) | -0.0012 (actual:creator_dump, 33s) | -0.0012 (actual:creator_dump, 33s) | -0.0012 (actual:creator_dump, 33s) |
| 4c3rRxkp | 1738s | -0.0029 (time_stop, 1804s) | -0.0014 (line_broken, 124s) | -0.0016 (actual:time_stop, 1804s) | -0.0016 (actual:time_stop, 1804s) | -0.0014 (time_stop, 124s) | -0.0014 (time_stop, 315s) | -0.0016 (actual:time_stop, 1804s) | -0.0014 (time_stop, 315s) | -0.0014 (time_stop, 124s) |
| ADxEynfQ | 36s | -0.0383 (trailing, 43s) | -0.0379 (actual:trailing, 43s) | -0.0379 (actual:trailing, 43s) | -0.0379 (actual:trailing, 43s) | -0.0379 (actual:trailing, 43s) | -0.0379 (actual:trailing, 43s) | -0.0379 (actual:trailing, 43s) | -0.0379 (actual:trailing, 43s) | -0.0379 (actual:trailing, 43s) |

## top-3 contribuintes (papel unico)
- a2_actual_exit_mcap_fee1.25: soma +0.1115; top3 = 4XYuRzrB +0.1201 (creator_dump, 0s); fsnuqm67 +0.0972 (target, 0s); H88Srjvu +0.0719 (line_broken, 0s)
- c_trail15: soma +0.3113; top3 = 4XYuRzrB +0.1201 (actual:creator_dump, 52s); fsnuqm67 +0.0972 (actual:target, 201s); 5hmWwRNw +0.0685 (actual:creator_dump, 49s)
- c_trail30: soma +0.2533; top3 = 4XYuRzrB +0.1201 (actual:creator_dump, 52s); fsnuqm67 +0.0972 (actual:target, 201s); H88Srjvu +0.0719 (actual:line_broken, 623s)
- d_tp+100%_else_trail30: soma +0.3722; top3 = 4XYuRzrB +0.1201 (actual:creator_dump, 52s); fsnuqm67 +0.0954 (target, 132s); 5hmWwRNw +0.0685 (actual:creator_dump, 49s)
- e_time5m: soma +0.0870; top3 = 4XYuRzrB +0.1201 (actual:creator_dump, 52s); fsnuqm67 +0.0972 (actual:target, 201s); 5hmWwRNw +0.0685 (actual:creator_dump, 49s)

## ranking (soma SOL, top3 < 50 %)
- papel (5 sets): melhor com top3<50%: h2_tp100_or_trail30_or_15m (+0.7732, top3 40%), d_tp+100%_else_trail30 (+0.7697, top3 40%), h3_tp100_or_trail30_or_30m (+0.7697, top3 40%), h_tp100_or_trail30_or_5m (+0.6521, top3 48%) | melhor absoluta: h2_tp100_or_trail30_or_15m (+0.7732, top3 40%)
- papel unico (mint@minuto): melhor com top3<50%: nenhuma | melhor absoluta: h2_tp100_or_trail30_or_15m (+0.3739, top3 76%)
- operator/5 real: melhor com top3<50%: nenhuma | melhor absoluta: e_time5m (-0.0172, top3 nan%)
- operator/5: melhor com top3<50%: nenhuma | melhor absoluta: e_time5m (+0.0330, top3 388%)
- flow_v2/5: melhor com top3<50%: nenhuma | melhor absoluta: d_tp+100%_else_trail30 (+0.2594, top3 84%)
- flow_v2/2: melhor com top3<50%: nenhuma | melhor absoluta: d_tp+100%_else_trail30 (+0.3837, top3 73%)
- flow_v2/6: melhor com top3<50%: nenhuma | melhor absoluta: c_trail15 (+0.0772, top3 188%)
- flow_v2/8: melhor com top3<50%: nenhuma | melhor absoluta: c_trail15 (+0.1034, top3 145%)

## delta pareado por aposta (regra - saida registrada a 1,25 %), modo=earlier

### papel unico (mint@minuto) (n=215)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 21 | 24 | 170 | +0.0000 | -0.0842 | 64% | 0.77 |
| b2_paper_full_set | 41 | 32 | 142 | +0.0000 | -0.1010 | 40% | 0.35 |
| c_trail15 | 44 | 26 | 145 | +0.0000 | +0.1999 | 22% | 0.04 |
| c_trail30 | 26 | 3 | 186 | +0.0000 | +0.1418 | 50% | 0.00 |
| c_trail50 | 8 | 2 | 205 | +0.0000 | +0.0204 | 89% | 0.11 |
| d_arm+25%_trail30 | 4 | 0 | 211 | +0.0000 | +0.0795 | 98% | 0.12 |
| d_arm+50%_trail30 | 2 | 0 | 213 | +0.0000 | +0.0563 | 100% | 0.50 |
| d_arm+100%_trail30 | 0 | 0 | 215 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 7 | 7 | 201 | +0.0000 | +0.0210 | 61% | 1.00 |
| d_arm+50%_trail15 | 4 | 5 | 206 | +0.0000 | -0.0230 | 80% | 1.00 |
| d_tp+25%_else_trail30 | 45 | 34 | 136 | +0.0000 | -0.0510 | 29% | 0.26 |
| d_tp+50%_else_trail30 | 39 | 20 | 156 | +0.0000 | +0.0820 | 41% | 0.02 |
| d_tp+100%_else_trail30 | 30 | 7 | 178 | +0.0000 | +0.2608 | 49% | 0.00 |
| e_time2m | 24 | 20 | 171 | +0.0000 | -0.2116 | 41% | 0.65 |
| e_time5m | 10 | 6 | 199 | +0.0000 | -0.0245 | 74% | 0.45 |
| e_time15m | 3 | 0 | 212 | +0.0000 | +0.0035 | 100% | 0.25 |
| e_time30m | 0 | 0 | 215 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 12 | 6 | 197 | +0.0000 | -0.0483 | 64% | 0.24 |
| f2_creator_sell_incl_15s_net_seller | 32 | 14 | 169 | +0.0000 | -0.1044 | 34% | 0.01 |
| g_tp30_or_trail20_or_5m | 51 | 42 | 122 | +0.0000 | +0.0055 | 25% | 0.41 |
| g2_tp30_or_trail20_or_2m | 57 | 42 | 116 | +0.0000 | -0.0471 | 24% | 0.16 |
| g3_tp50_or_trail20_or_5m | 46 | 34 | 135 | +0.0000 | +0.1157 | 30% | 0.22 |
| g4_tp30_or_trail15_or_5m | 57 | 48 | 110 | +0.0000 | +0.0657 | 22% | 0.44 |
| g5_tp30_or_trail15_or_2m | 64 | 47 | 104 | +0.0000 | +0.0257 | 21% | 0.13 |
| h_tp100_or_trail30_or_5m | 33 | 11 | 171 | +0.0000 | +0.2098 | 43% | 0.00 |
| h2_tp100_or_trail30_or_15m | 30 | 7 | 178 | +0.0000 | +0.2625 | 48% | 0.00 |
| h3_tp100_or_trail30_or_30m | 30 | 7 | 178 | +0.0000 | +0.2608 | 49% | 0.00 |
| h4_tp300_or_trail30_or_30m | 27 | 3 | 185 | +0.0000 | +0.1538 | 46% | 0.00 |

### operator/5 real (n=12)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 4 | 1 | 7 | +0.0000 | +0.0161 | 99% | 0.38 |
| b2_paper_full_set | 5 | 2 | 5 | +0.0000 | -0.0003 | 98% | 0.45 |
| c_trail15 | 3 | 1 | 8 | +0.0000 | +0.0121 | 100% | 0.62 |
| c_trail30 | 3 | 0 | 9 | +0.0000 | +0.0003 | 100% | 0.25 |
| c_trail50 | 0 | 0 | 12 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail30 | 2 | 0 | 10 | +0.0000 | +0.0002 | 100% | 0.50 |
| d_arm+50%_trail30 | 0 | 0 | 12 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+100%_trail30 | 0 | 0 | 12 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 2 | 0 | 10 | +0.0000 | +0.0158 | 100% | 0.50 |
| d_arm+50%_trail15 | 0 | 0 | 12 | +0.0000 | +0.0000 | nan% | nan |
| d_tp+25%_else_trail30 | 3 | 1 | 8 | +0.0000 | +0.0207 | 100% | 0.62 |
| d_tp+50%_else_trail30 | 4 | 0 | 8 | +0.0000 | +0.0032 | 98% | 0.12 |
| d_tp+100%_else_trail30 | 3 | 0 | 9 | +0.0000 | +0.0003 | 100% | 0.25 |
| e_time2m | 4 | 1 | 7 | +0.0000 | +0.0164 | 99% | 0.38 |
| e_time5m | 5 | 0 | 7 | +0.0000 | +0.0414 | 95% | 0.06 |
| e_time15m | 3 | 0 | 9 | +0.0000 | +0.0021 | 100% | 0.25 |
| e_time30m | 0 | 0 | 12 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 2 | 2 | 8 | +0.0000 | -0.0163 | 100% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 3 | 2 | 7 | +0.0000 | -0.0139 | 100% | 1.00 |
| g_tp30_or_trail20_or_5m | 4 | 2 | 6 | +0.0000 | +0.0042 | 99% | 0.69 |
| g2_tp30_or_trail20_or_2m | 4 | 2 | 6 | +0.0000 | -0.0024 | 99% | 0.69 |
| g3_tp50_or_trail20_or_5m | 5 | 1 | 6 | +0.0000 | +0.0198 | 88% | 0.22 |
| g4_tp30_or_trail15_or_5m | 4 | 2 | 6 | +0.0000 | +0.0036 | 99% | 0.69 |
| g5_tp30_or_trail15_or_2m | 4 | 2 | 6 | +0.0000 | +0.0037 | 99% | 0.69 |
| h_tp100_or_trail30_or_5m | 5 | 0 | 7 | +0.0000 | +0.0414 | 95% | 0.06 |
| h2_tp100_or_trail30_or_15m | 5 | 0 | 7 | +0.0000 | +0.0023 | 92% | 0.06 |
| h3_tp100_or_trail30_or_30m | 3 | 0 | 9 | +0.0000 | +0.0003 | 100% | 0.25 |
| h4_tp300_or_trail30_or_30m | 3 | 0 | 9 | +0.0000 | +0.0003 | 100% | 0.25 |

### operator/5 (n=19)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 2 | 3 | 14 | +0.0000 | +0.0263 | 100% | 1.00 |
| b2_paper_full_set | 5 | 3 | 11 | +0.0000 | +0.0339 | 99% | 0.73 |
| c_trail15 | 3 | 3 | 13 | +0.0000 | -0.0430 | 100% | 1.00 |
| c_trail30 | 1 | 0 | 18 | +0.0000 | +0.0001 | 100% | 1.00 |
| c_trail50 | 0 | 0 | 19 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail30 | 0 | 0 | 19 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+50%_trail30 | 0 | 0 | 19 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+100%_trail30 | 0 | 0 | 19 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 0 | 1 | 18 | +0.0000 | -0.0363 | nan% | 1.00 |
| d_arm+50%_trail15 | 0 | 1 | 18 | +0.0000 | -0.0363 | nan% | 1.00 |
| d_tp+25%_else_trail30 | 3 | 2 | 14 | +0.0000 | -0.0390 | 100% | 1.00 |
| d_tp+50%_else_trail30 | 2 | 1 | 16 | +0.0000 | -0.0026 | 100% | 1.00 |
| d_tp+100%_else_trail30 | 2 | 0 | 17 | +0.0000 | +0.0334 | 100% | 0.50 |
| e_time2m | 3 | 2 | 14 | +0.0000 | -0.0369 | 100% | 1.00 |
| e_time5m | 2 | 0 | 17 | +0.0000 | +0.0453 | 100% | 0.50 |
| e_time15m | 1 | 0 | 18 | +0.0000 | +0.0019 | 100% | 1.00 |
| e_time30m | 0 | 0 | 19 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 3 | 0 | 16 | +0.0000 | +0.0076 | 100% | 0.25 |
| f2_creator_sell_incl_15s_net_seller | 5 | 0 | 14 | +0.0000 | +0.0096 | 90% | 0.06 |
| g_tp30_or_trail20_or_5m | 4 | 3 | 12 | +0.0000 | -0.0261 | 87% | 1.00 |
| g2_tp30_or_trail20_or_2m | 4 | 4 | 11 | +0.0000 | -0.0398 | 94% | 1.00 |
| g3_tp50_or_trail20_or_5m | 2 | 3 | 14 | +0.0000 | -0.0014 | 100% | 1.00 |
| g4_tp30_or_trail15_or_5m | 5 | 3 | 11 | +0.0000 | -0.0389 | 80% | 0.73 |
| g5_tp30_or_trail15_or_2m | 6 | 3 | 10 | +0.0000 | -0.0383 | 78% | 0.51 |
| h_tp100_or_trail30_or_5m | 2 | 0 | 17 | +0.0000 | +0.0351 | 100% | 0.50 |
| h2_tp100_or_trail30_or_15m | 2 | 0 | 17 | +0.0000 | +0.0351 | 100% | 0.50 |
| h3_tp100_or_trail30_or_30m | 2 | 0 | 17 | +0.0000 | +0.0334 | 100% | 0.50 |
| h4_tp300_or_trail30_or_30m | 1 | 0 | 18 | +0.0000 | +0.0001 | 100% | 1.00 |

### flow_v2/5 (n=137)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 6 | 15 | 116 | +0.0000 | -0.0935 | 97% | 0.08 |
| b2_paper_full_set | 17 | 22 | 98 | +0.0000 | -0.1192 | 60% | 0.52 |
| c_trail15 | 25 | 23 | 89 | +0.0000 | +0.0047 | 36% | 0.89 |
| c_trail30 | 15 | 3 | 119 | +0.0000 | +0.0738 | 63% | 0.01 |
| c_trail50 | 5 | 2 | 130 | +0.0000 | +0.0163 | 100% | 0.45 |
| d_arm+25%_trail30 | 2 | 0 | 135 | +0.0000 | +0.0339 | 100% | 0.50 |
| d_arm+50%_trail30 | 1 | 0 | 136 | +0.0000 | +0.0324 | 100% | 1.00 |
| d_arm+100%_trail30 | 0 | 0 | 137 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 4 | 7 | 126 | +0.0000 | -0.0736 | 98% | 0.55 |
| d_arm+50%_trail15 | 2 | 5 | 130 | +0.0000 | -0.0875 | 100% | 0.45 |
| d_tp+25%_else_trail30 | 26 | 28 | 83 | +0.0000 | -0.1396 | 41% | 0.89 |
| d_tp+50%_else_trail30 | 23 | 17 | 97 | +0.0000 | -0.0280 | 61% | 0.43 |
| d_tp+100%_else_trail30 | 18 | 7 | 112 | +0.0000 | +0.1859 | 64% | 0.04 |
| e_time2m | 13 | 15 | 109 | +0.0000 | -0.1575 | 54% | 0.85 |
| e_time5m | 5 | 5 | 127 | +0.0000 | -0.0307 | 91% | 1.00 |
| e_time15m | 1 | 0 | 136 | +0.0000 | +0.0015 | 100% | 1.00 |
| e_time30m | 0 | 0 | 137 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 5 | 5 | 127 | +0.0000 | -0.0539 | 100% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 13 | 11 | 113 | +0.0000 | -0.0923 | 53% | 0.84 |
| g_tp30_or_trail20_or_5m | 29 | 35 | 73 | +0.0000 | -0.1201 | 34% | 0.53 |
| g2_tp30_or_trail20_or_2m | 32 | 34 | 71 | +0.0000 | -0.1419 | 33% | 0.90 |
| g3_tp50_or_trail20_or_5m | 27 | 29 | 81 | +0.0000 | -0.0477 | 44% | 0.89 |
| g4_tp30_or_trail15_or_5m | 31 | 40 | 66 | +0.0000 | -0.0931 | 31% | 0.34 |
| g5_tp30_or_trail15_or_2m | 35 | 38 | 64 | +0.0000 | -0.1006 | 30% | 0.82 |
| h_tp100_or_trail30_or_5m | 20 | 10 | 107 | +0.0000 | +0.1375 | 56% | 0.10 |
| h2_tp100_or_trail30_or_15m | 18 | 7 | 112 | +0.0000 | +0.1859 | 64% | 0.04 |
| h3_tp100_or_trail30_or_30m | 18 | 7 | 112 | +0.0000 | +0.1859 | 64% | 0.04 |
| h4_tp300_or_trail30_or_30m | 16 | 3 | 118 | +0.0000 | +0.0858 | 56% | 0.00 |

### flow_v2/2 (n=163)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 11 | 18 | 134 | +0.0000 | -0.0909 | 80% | 0.26 |
| b2_paper_full_set | 25 | 26 | 112 | +0.0000 | -0.1216 | 53% | 1.00 |
| c_trail15 | 31 | 25 | 107 | +0.0000 | +0.0796 | 28% | 0.50 |
| c_trail30 | 19 | 3 | 141 | +0.0000 | +0.0979 | 59% | 0.00 |
| c_trail50 | 6 | 2 | 155 | +0.0000 | +0.0163 | 100% | 0.29 |
| d_arm+25%_trail30 | 3 | 0 | 160 | +0.0000 | +0.0556 | 100% | 0.25 |
| d_arm+50%_trail30 | 1 | 0 | 162 | +0.0000 | +0.0324 | 100% | 1.00 |
| d_arm+100%_trail30 | 0 | 0 | 163 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 5 | 7 | 151 | +0.0000 | -0.0435 | 84% | 0.77 |
| d_arm+50%_trail15 | 2 | 5 | 156 | +0.0000 | -0.0875 | 100% | 0.45 |
| d_tp+25%_else_trail30 | 33 | 29 | 101 | +0.0000 | -0.0897 | 35% | 0.70 |
| d_tp+50%_else_trail30 | 30 | 17 | 116 | +0.0000 | +0.0173 | 51% | 0.08 |
| d_tp+100%_else_trail30 | 22 | 7 | 134 | +0.0000 | +0.2100 | 58% | 0.01 |
| e_time2m | 16 | 17 | 130 | +0.0000 | -0.1593 | 44% | 1.00 |
| e_time5m | 7 | 5 | 151 | +0.0000 | -0.0133 | 75% | 0.77 |
| e_time15m | 1 | 0 | 162 | +0.0000 | +0.0015 | 100% | 1.00 |
| e_time30m | 0 | 0 | 163 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 7 | 6 | 150 | +0.0000 | -0.0590 | 92% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 21 | 12 | 130 | +0.0000 | -0.0810 | 41% | 0.16 |
| g_tp30_or_trail20_or_5m | 37 | 37 | 89 | +0.0000 | -0.0586 | 29% | 1.00 |
| g2_tp30_or_trail20_or_2m | 40 | 37 | 86 | +0.0000 | -0.1047 | 28% | 0.82 |
| g3_tp50_or_trail20_or_5m | 35 | 30 | 98 | +0.0000 | +0.0341 | 35% | 0.62 |
| g4_tp30_or_trail15_or_5m | 40 | 43 | 80 | +0.0000 | -0.0172 | 26% | 0.83 |
| g5_tp30_or_trail15_or_2m | 44 | 42 | 77 | +0.0000 | -0.0509 | 25% | 0.91 |
| h_tp100_or_trail30_or_5m | 25 | 10 | 128 | +0.0000 | +0.1773 | 49% | 0.02 |
| h2_tp100_or_trail30_or_15m | 22 | 7 | 134 | +0.0000 | +0.2100 | 58% | 0.01 |
| h3_tp100_or_trail30_or_30m | 22 | 7 | 134 | +0.0000 | +0.2100 | 58% | 0.01 |
| h4_tp300_or_trail30_or_30m | 20 | 3 | 140 | +0.0000 | +0.1099 | 53% | 0.00 |

### flow_v2/6 (n=25)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 7 | 1 | 17 | +0.0000 | +0.0072 | 100% | 0.07 |
| b2_paper_full_set | 8 | 1 | 16 | +0.0000 | +0.0073 | 99% | 0.04 |
| c_trail15 | 6 | 1 | 18 | +0.0000 | +0.0526 | 74% | 0.12 |
| c_trail30 | 4 | 0 | 21 | +0.0000 | +0.0261 | 100% | 0.12 |
| c_trail50 | 1 | 0 | 24 | +0.0000 | +0.0009 | 100% | 1.00 |
| d_arm+25%_trail30 | 1 | 0 | 24 | +0.0000 | +0.0239 | 100% | 1.00 |
| d_arm+50%_trail30 | 1 | 0 | 24 | +0.0000 | +0.0239 | 100% | 1.00 |
| d_arm+100%_trail30 | 0 | 0 | 25 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 1 | 0 | 24 | +0.0000 | +0.0239 | 100% | 1.00 |
| d_arm+50%_trail15 | 1 | 0 | 24 | +0.0000 | +0.0239 | 100% | 1.00 |
| d_tp+25%_else_trail30 | 5 | 4 | 16 | +0.0000 | -0.0396 | 99% | 1.00 |
| d_tp+50%_else_trail30 | 4 | 3 | 18 | +0.0000 | -0.0117 | 100% | 1.00 |
| d_tp+100%_else_trail30 | 5 | 0 | 20 | +0.0000 | +0.0329 | 99% | 0.06 |
| e_time2m | 6 | 2 | 17 | +0.0000 | -0.0464 | 84% | 0.29 |
| e_time5m | 3 | 1 | 21 | +0.0000 | -0.0112 | 100% | 0.62 |
| e_time15m | 2 | 0 | 23 | +0.0000 | +0.0019 | 100% | 0.50 |
| e_time30m | 0 | 0 | 25 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 1 | 0 | 24 | +0.0000 | +0.0000 | 100% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 4 | 1 | 20 | +0.0000 | -0.0303 | 99% | 0.38 |
| g_tp30_or_trail20_or_5m | 5 | 4 | 16 | +0.0000 | -0.0278 | 91% | 1.00 |
| g2_tp30_or_trail20_or_2m | 7 | 4 | 14 | +0.0000 | -0.0348 | 91% | 0.55 |
| g3_tp50_or_trail20_or_5m | 5 | 3 | 17 | +0.0000 | +0.0010 | 92% | 0.73 |
| g4_tp30_or_trail15_or_5m | 6 | 5 | 14 | +0.0000 | -0.0140 | 80% | 1.00 |
| g5_tp30_or_trail15_or_2m | 8 | 5 | 12 | +0.0000 | -0.0210 | 80% | 0.58 |
| h_tp100_or_trail30_or_5m | 5 | 1 | 19 | +0.0000 | +0.0147 | 98% | 0.22 |
| h2_tp100_or_trail30_or_15m | 5 | 0 | 20 | +0.0000 | +0.0346 | 94% | 0.06 |
| h3_tp100_or_trail30_or_30m | 5 | 0 | 20 | +0.0000 | +0.0329 | 99% | 0.06 |
| h4_tp300_or_trail30_or_30m | 4 | 0 | 21 | +0.0000 | +0.0261 | 100% | 0.12 |

### flow_v2/8 (n=31)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 8 | 5 | 18 | +0.0000 | +0.0059 | 86% | 0.58 |
| b2_paper_full_set | 10 | 5 | 16 | +0.0000 | +0.0122 | 70% | 0.30 |
| c_trail15 | 8 | 0 | 23 | +0.0000 | +0.0801 | 82% | 0.01 |
| c_trail30 | 4 | 0 | 27 | +0.0000 | +0.0179 | 100% | 0.12 |
| c_trail50 | 1 | 0 | 30 | +0.0000 | +0.0032 | 100% | 1.00 |
| d_arm+25%_trail30 | 0 | 0 | 31 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+50%_trail30 | 0 | 0 | 31 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+100%_trail30 | 0 | 0 | 31 | +0.0000 | +0.0000 | nan% | nan |
| d_arm+25%_trail15 | 1 | 0 | 30 | +0.0000 | +0.0405 | 100% | 1.00 |
| d_arm+50%_trail15 | 1 | 0 | 30 | +0.0000 | +0.0405 | 100% | 1.00 |
| d_tp+25%_else_trail30 | 7 | 5 | 19 | +0.0000 | +0.0049 | 96% | 0.77 |
| d_tp+50%_else_trail30 | 6 | 3 | 22 | +0.0000 | +0.0220 | 97% | 0.51 |
| d_tp+100%_else_trail30 | 5 | 0 | 26 | +0.0000 | +0.0247 | 96% | 0.06 |
| e_time2m | 3 | 3 | 25 | +0.0000 | -0.0593 | 100% | 1.00 |
| e_time5m | 2 | 1 | 28 | +0.0000 | -0.0130 | 100% | 1.00 |
| e_time15m | 1 | 0 | 30 | +0.0000 | +0.0001 | 100% | 1.00 |
| e_time30m | 0 | 0 | 31 | +0.0000 | +0.0000 | nan% | nan |
| f_first_creator_sell | 1 | 0 | 30 | +0.0000 | +0.0030 | 100% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 5 | 2 | 24 | +0.0000 | -0.0350 | 95% | 0.45 |
| g_tp30_or_trail20_or_5m | 9 | 4 | 18 | +0.0000 | +0.0093 | 86% | 0.27 |
| g2_tp30_or_trail20_or_2m | 10 | 4 | 17 | +0.0000 | +0.0022 | 86% | 0.18 |
| g3_tp50_or_trail20_or_5m | 8 | 3 | 20 | +0.0000 | +0.0310 | 89% | 0.23 |
| g4_tp30_or_trail15_or_5m | 10 | 4 | 17 | +0.0000 | +0.0220 | 79% | 0.18 |
| g5_tp30_or_trail15_or_2m | 11 | 4 | 16 | +0.0000 | +0.0148 | 79% | 0.12 |
| h_tp100_or_trail30_or_5m | 5 | 1 | 25 | +0.0000 | +0.0048 | 97% | 0.22 |
| h2_tp100_or_trail30_or_15m | 5 | 0 | 26 | +0.0000 | +0.0247 | 96% | 0.06 |
| h3_tp100_or_trail30_or_30m | 5 | 0 | 26 | +0.0000 | +0.0247 | 96% | 0.06 |
| h4_tp300_or_trail30_or_30m | 4 | 0 | 27 | +0.0000 | +0.0179 | 100% | 0.12 |
