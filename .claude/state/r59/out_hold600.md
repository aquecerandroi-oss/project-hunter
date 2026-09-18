## cobertura
modo=hold min_cover=600s taxa=1.25% por perna
| set | apostas | elegiveis | sem serie | cobertura mediana (s) | hold mediano (s) |
|---|---|---|---|---|---|
| operator/5 real | 12 | 3 | 0 | 304 | 102 |
| operator/5 | 19 | 3 | 0 | 298 | 73 |
| flow_v2/5 | 139 | 20 | 1 | 194 | 76 |
| flow_v2/2 | 165 | 24 | 1 | 183 | 76 |
| flow_v2/6 | 25 | 6 | 0 | 222 | 79 |
| flow_v2/8 | 31 | 5 | 0 | 199 | 76 |

## operator/5 real
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 3 | 0% | -0.217 | -0.0326 | 0.0326 | — | time_stop=3 |
| a2_actual_exit_mcap_fee1.25 | 3 | 0% | -0.196 | -0.0294 | 0.0294 | — | time_stop=3 |
| b_line_broken(2) | 3 | 0% | -0.169 | -0.0254 | 0.0254 | — | censored=1, line_broken=2 |
| b2_paper_full_set | 3 | 0% | -0.169 | -0.0254 | 0.0254 | — | censored=1, line_broken=2 |
| c_trail15 | 3 | 0% | -0.138 | -0.0207 | 0.0207 | — | censored=1, trailing=2 |
| c_trail30 | 3 | 0% | -0.193 | -0.0290 | 0.0290 | — | censored=2, trailing=1 |
| c_trail50 | 3 | 0% | -0.194 | -0.0290 | 0.0290 | — | censored=3 |
| d_arm+25%_trail30 | 3 | 0% | -0.194 | -0.0290 | 0.0290 | — | censored=3 |
| d_arm+50%_trail30 | 3 | 0% | -0.194 | -0.0290 | 0.0290 | — | censored=3 |
| d_arm+100%_trail30 | 3 | 0% | -0.194 | -0.0290 | 0.0290 | — | censored=3 |
| d_arm+25%_trail15 | 3 | 0% | -0.194 | -0.0290 | 0.0290 | — | censored=3 |
| d_arm+50%_trail15 | 3 | 0% | -0.194 | -0.0290 | 0.0290 | — | censored=3 |
| d_tp+25%_else_trail30 | 3 | 0% | -0.193 | -0.0290 | 0.0290 | — | censored=2, trailing=1 |
| d_tp+50%_else_trail30 | 3 | 0% | -0.193 | -0.0290 | 0.0290 | — | censored=2, trailing=1 |
| d_tp+100%_else_trail30 | 3 | 0% | -0.193 | -0.0290 | 0.0290 | — | censored=2, trailing=1 |
| e_time2m | 3 | 0% | -0.178 | -0.0267 | 0.0267 | — | time_stop=3 |
| e_time5m | 3 | 0% | -0.135 | -0.0202 | 0.0202 | — | time_stop=3 |
| e_time15m | 3 | 0% | -0.182 | -0.0273 | 0.0273 | — | time_stop=3 |
| e_time30m | 3 | 0% | -0.194 | -0.0290 | 0.0290 | — | censored=3 |
| f_first_creator_sell | 3 | 0% | -0.194 | -0.0290 | 0.0290 | — | censored=3 |
| f2_creator_sell_incl_15s_net_seller | 3 | 0% | -0.194 | -0.0290 | 0.0290 | — | censored=3 |
| g_tp30_or_trail20_or_5m | 3 | 0% | -0.123 | -0.0185 | 0.0185 | — | time_stop=2, trailing=1 |
| g2_tp30_or_trail20_or_2m | 3 | 0% | -0.167 | -0.0250 | 0.0250 | — | time_stop=2, trailing=1 |
| g3_tp50_or_trail20_or_5m | 3 | 0% | -0.123 | -0.0185 | 0.0185 | — | time_stop=2, trailing=1 |
| g4_tp30_or_trail15_or_5m | 3 | 0% | -0.138 | -0.0207 | 0.0207 | — | time_stop=1, trailing=2 |
| g5_tp30_or_trail15_or_2m | 3 | 0% | -0.138 | -0.0207 | 0.0207 | — | time_stop=1, trailing=2 |
| h_tp100_or_trail30_or_5m | 3 | 0% | -0.135 | -0.0202 | 0.0202 | — | time_stop=3 |
| h2_tp100_or_trail30_or_15m | 3 | 0% | -0.182 | -0.0273 | 0.0273 | — | time_stop=3 |
| h3_tp100_or_trail30_or_30m | 3 | 0% | -0.193 | -0.0290 | 0.0290 | — | censored=2, trailing=1 |
| h4_tp300_or_trail30_or_30m | 3 | 0% | -0.193 | -0.0290 | 0.0290 | — | censored=2, trailing=1 |

## operator/5
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 3 | 0% | -0.166 | -0.0250 | 0.0250 | — | line_broken=2, time_stop=1 |
| a2_actual_exit_mcap_fee1.25 | 3 | 0% | -0.156 | -0.0234 | 0.0234 | — | line_broken=2, time_stop=1 |
| b_line_broken(2) | 3 | 0% | -0.155 | -0.0233 | 0.0233 | — | censored=1, line_broken=2 |
| b2_paper_full_set | 3 | 0% | -0.155 | -0.0233 | 0.0233 | — | censored=1, line_broken=2 |
| c_trail15 | 3 | 0% | -0.138 | -0.0207 | 0.0207 | — | censored=1, trailing=2 |
| c_trail30 | 3 | 0% | -0.180 | -0.0271 | 0.0271 | — | censored=2, trailing=1 |
| c_trail50 | 3 | 0% | -0.181 | -0.0271 | 0.0271 | — | censored=3 |
| d_arm+25%_trail30 | 3 | 0% | -0.181 | -0.0271 | 0.0271 | — | censored=3 |
| d_arm+50%_trail30 | 3 | 0% | -0.181 | -0.0271 | 0.0271 | — | censored=3 |
| d_arm+100%_trail30 | 3 | 0% | -0.181 | -0.0271 | 0.0271 | — | censored=3 |
| d_arm+25%_trail15 | 3 | 0% | -0.181 | -0.0271 | 0.0271 | — | censored=3 |
| d_arm+50%_trail15 | 3 | 0% | -0.181 | -0.0271 | 0.0271 | — | censored=3 |
| d_tp+25%_else_trail30 | 3 | 0% | -0.180 | -0.0271 | 0.0271 | — | censored=2, trailing=1 |
| d_tp+50%_else_trail30 | 3 | 0% | -0.180 | -0.0271 | 0.0271 | — | censored=2, trailing=1 |
| d_tp+100%_else_trail30 | 3 | 0% | -0.180 | -0.0271 | 0.0271 | — | censored=2, trailing=1 |
| e_time2m | 3 | 0% | -0.165 | -0.0248 | 0.0248 | — | time_stop=3 |
| e_time5m | 3 | 0% | -0.120 | -0.0179 | 0.0179 | — | time_stop=3 |
| e_time15m | 3 | 0% | -0.169 | -0.0254 | 0.0254 | — | time_stop=3 |
| e_time30m | 3 | 0% | -0.181 | -0.0271 | 0.0271 | — | censored=3 |
| f_first_creator_sell | 3 | 0% | -0.181 | -0.0271 | 0.0271 | — | censored=3 |
| f2_creator_sell_incl_15s_net_seller | 3 | 0% | -0.181 | -0.0271 | 0.0271 | — | censored=3 |
| g_tp30_or_trail20_or_5m | 3 | 0% | -0.108 | -0.0163 | 0.0163 | — | time_stop=2, trailing=1 |
| g2_tp30_or_trail20_or_2m | 3 | 0% | -0.154 | -0.0231 | 0.0231 | — | time_stop=2, trailing=1 |
| g3_tp50_or_trail20_or_5m | 3 | 0% | -0.108 | -0.0163 | 0.0163 | — | time_stop=2, trailing=1 |
| g4_tp30_or_trail15_or_5m | 3 | 0% | -0.138 | -0.0207 | 0.0207 | — | time_stop=1, trailing=2 |
| g5_tp30_or_trail15_or_2m | 3 | 0% | -0.136 | -0.0204 | 0.0204 | — | time_stop=2, trailing=1 |
| h_tp100_or_trail30_or_5m | 3 | 0% | -0.120 | -0.0179 | 0.0179 | — | time_stop=3 |
| h2_tp100_or_trail30_or_15m | 3 | 0% | -0.169 | -0.0254 | 0.0254 | — | time_stop=3 |
| h3_tp100_or_trail30_or_30m | 3 | 0% | -0.180 | -0.0271 | 0.0271 | — | censored=2, trailing=1 |
| h4_tp300_or_trail30_or_30m | 3 | 0% | -0.180 | -0.0271 | 0.0271 | — | censored=2, trailing=1 |

## flow_v2/5
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 20 | 50% | +0.130 | +0.1300 | 0.0297 | 124% | creator_dump=3, line_broken=15, time_stop=2 |
| a2_actual_exit_mcap_fee1.25 | 20 | 60% | +0.143 | +0.1434 | 0.0295 | 115% | creator_dump=3, line_broken=15, time_stop=2 |
| b_line_broken(2) | 20 | 60% | +0.135 | +0.1346 | 0.0367 | 125% | censored=3, line_broken=17 |
| b2_paper_full_set | 20 | 55% | +0.123 | +0.1230 | 0.0367 | 134% | censored=2, creator_dump=3, line_broken=15 |
| c_trail15 | 20 | 50% | +0.081 | +0.0810 | 0.0408 | 171% | censored=1, trailing=19 |
| c_trail30 | 20 | 45% | +0.032 | +0.0316 | 0.1015 | 806% | censored=8, trailing=12 |
| c_trail50 | 20 | 45% | +0.036 | +0.0358 | 0.1110 | 710% | censored=11, trailing=9 |
| d_arm+25%_trail30 | 20 | 45% | +0.040 | +0.0401 | 0.0923 | 634% | censored=12, trailing=8 |
| d_arm+50%_trail30 | 20 | 50% | +0.098 | +0.0981 | 0.0923 | 259% | censored=13, trailing=7 |
| d_arm+100%_trail30 | 20 | 45% | +0.085 | +0.0847 | 0.1111 | 300% | censored=17, trailing=3 |
| d_arm+25%_trail15 | 20 | 55% | +0.033 | +0.0331 | 0.0589 | 420% | censored=7, trailing=13 |
| d_arm+50%_trail15 | 20 | 55% | +0.069 | +0.0691 | 0.0753 | 257% | censored=8, trailing=12 |
| d_tp+25%_else_trail30 | 20 | 75% | +0.112 | +0.1122 | 0.0295 | 55% | censored=2, target=14, trailing=4 |
| d_tp+50%_else_trail30 | 20 | 65% | +0.172 | +0.1722 | 0.0448 | 52% | censored=2, target=12, trailing=6 |
| d_tp+100%_else_trail30 | 20 | 50% | +0.025 | +0.0251 | 0.0809 | 642% | censored=5, target=4, trailing=11 |
| e_time2m | 20 | 50% | +0.035 | +0.0351 | 0.0298 | 215% | time_stop=20 |
| e_time5m | 20 | 60% | +0.096 | +0.0963 | 0.0735 | 101% | time_stop=20 |
| e_time15m | 20 | 55% | +0.390 | +0.3895 | 0.0754 | 78% | censored=7, time_stop=13 |
| e_time30m | 20 | 45% | +0.080 | +0.0799 | 0.1111 | 319% | censored=19, time_stop=1 |
| f_first_creator_sell | 20 | 50% | +0.126 | +0.1255 | 0.0828 | 183% | censored=14, creator_sell=6 |
| f2_creator_sell_incl_15s_net_seller | 20 | 55% | +0.108 | +0.1082 | 0.0828 | 213% | censored=14, creator_sell=6 |
| g_tp30_or_trail20_or_5m | 20 | 70% | +0.130 | +0.1302 | 0.0135 | 45% | target=10, time_stop=6, trailing=4 |
| g2_tp30_or_trail20_or_2m | 20 | 55% | +0.054 | +0.0536 | 0.0162 | 94% | target=4, time_stop=12, trailing=4 |
| g3_tp50_or_trail20_or_5m | 20 | 65% | +0.168 | +0.1680 | 0.0135 | 47% | target=5, time_stop=10, trailing=5 |
| g4_tp30_or_trail15_or_5m | 20 | 65% | +0.101 | +0.1013 | 0.0223 | 54% | target=9, time_stop=5, trailing=6 |
| g5_tp30_or_trail15_or_2m | 20 | 55% | +0.048 | +0.0475 | 0.0223 | 106% | target=4, time_stop=11, trailing=5 |
| h_tp100_or_trail30_or_5m | 20 | 60% | +0.078 | +0.0783 | 0.0764 | 123% | time_stop=15, trailing=5 |
| h2_tp100_or_trail30_or_15m | 20 | 50% | +0.115 | +0.1155 | 0.0809 | 139% | target=4, time_stop=7, trailing=9 |
| h3_tp100_or_trail30_or_30m | 20 | 50% | +0.025 | +0.0251 | 0.0809 | 642% | censored=5, target=4, trailing=11 |
| h4_tp300_or_trail30_or_30m | 20 | 45% | +0.028 | +0.0281 | 0.1015 | 893% | censored=7, target=1, trailing=12 |

## flow_v2/2
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 24 | 46% | +0.086 | +0.1034 | 0.0666 | 155% | creator_dump=4, line_broken=18, time_stop=2 |
| a2_actual_exit_mcap_fee1.25 | 24 | 54% | +0.099 | +0.1189 | 0.0650 | 138% | creator_dump=4, line_broken=18, time_stop=2 |
| b_line_broken(2) | 24 | 54% | +0.099 | +0.1190 | 0.0640 | 141% | censored=4, line_broken=20 |
| b2_paper_full_set | 24 | 50% | +0.089 | +0.1074 | 0.0653 | 156% | censored=2, creator_dump=4, line_broken=18 |
| c_trail15 | 24 | 50% | +0.097 | +0.1163 | 0.0511 | 119% | censored=3, trailing=21 |
| c_trail30 | 24 | 46% | +0.041 | +0.0490 | 0.1015 | 519% | censored=10, trailing=14 |
| c_trail50 | 24 | 46% | +0.040 | +0.0476 | 0.1110 | 534% | censored=15, trailing=9 |
| d_arm+25%_trail30 | 24 | 46% | +0.043 | +0.0519 | 0.1040 | 490% | censored=16, trailing=8 |
| d_arm+50%_trail30 | 24 | 50% | +0.092 | +0.1099 | 0.1040 | 232% | censored=17, trailing=7 |
| d_arm+100%_trail30 | 24 | 46% | +0.080 | +0.0965 | 0.1111 | 264% | censored=21, trailing=3 |
| d_arm+25%_trail15 | 24 | 54% | +0.037 | +0.0449 | 0.1040 | 310% | censored=11, trailing=13 |
| d_arm+50%_trail15 | 24 | 54% | +0.067 | +0.0809 | 0.1040 | 220% | censored=12, trailing=12 |
| d_tp+25%_else_trail30 | 24 | 71% | +0.112 | +0.1349 | 0.0567 | 62% | censored=2, target=16, trailing=6 |
| d_tp+50%_else_trail30 | 24 | 62% | +0.162 | +0.1949 | 0.0567 | 49% | censored=2, target=14, trailing=8 |
| d_tp+100%_else_trail30 | 24 | 50% | +0.035 | +0.0425 | 0.0975 | 379% | censored=7, target=4, trailing=13 |
| e_time2m | 24 | 50% | +0.042 | +0.0502 | 0.0388 | 162% | time_stop=24 |
| e_time5m | 24 | 58% | +0.106 | +0.1274 | 0.0735 | 83% | time_stop=24 |
| e_time15m | 24 | 54% | +0.335 | +0.4017 | 0.0754 | 76% | censored=10, time_stop=14 |
| e_time30m | 24 | 46% | +0.076 | +0.0917 | 0.1111 | 278% | censored=23, time_stop=1 |
| f_first_creator_sell | 24 | 50% | +0.112 | +0.1346 | 0.0798 | 171% | censored=15, creator_sell=9 |
| f2_creator_sell_incl_15s_net_seller | 24 | 54% | +0.104 | +0.1253 | 0.0798 | 186% | censored=15, creator_sell=9 |
| g_tp30_or_trail20_or_5m | 24 | 67% | +0.141 | +0.1690 | 0.0366 | 49% | target=12, time_stop=7, trailing=5 |
| g2_tp30_or_trail20_or_2m | 24 | 54% | +0.054 | +0.0652 | 0.0349 | 96% | target=5, time_stop=14, trailing=5 |
| g3_tp50_or_trail20_or_5m | 24 | 62% | +0.172 | +0.2068 | 0.0366 | 43% | target=7, time_stop=11, trailing=6 |
| g4_tp30_or_trail15_or_5m | 24 | 62% | +0.118 | +0.1419 | 0.0349 | 58% | target=11, time_stop=5, trailing=8 |
| g5_tp30_or_trail15_or_2m | 24 | 54% | +0.049 | +0.0591 | 0.0349 | 106% | target=5, time_stop=12, trailing=7 |
| h_tp100_or_trail30_or_5m | 24 | 58% | +0.093 | +0.1121 | 0.0764 | 94% | time_stop=18, trailing=6 |
| h2_tp100_or_trail30_or_15m | 24 | 50% | +0.111 | +0.1329 | 0.0809 | 121% | censored=2, target=4, time_stop=7, trailing=11 |
| h3_tp100_or_trail30_or_30m | 24 | 50% | +0.035 | +0.0425 | 0.0975 | 379% | censored=7, target=4, trailing=13 |
| h4_tp300_or_trail30_or_30m | 24 | 46% | +0.038 | +0.0455 | 0.1015 | 552% | censored=9, target=1, trailing=14 |

## flow_v2/6
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 6 | 17% | -0.056 | -0.0167 | 0.0599 | — | line_broken=3, time_stop=3 |
| a2_actual_exit_mcap_fee1.25 | 6 | 17% | -0.044 | -0.0131 | 0.0575 | — | line_broken=3, time_stop=3 |
| b_line_broken(2) | 6 | 17% | -0.031 | -0.0092 | 0.0536 | — | censored=3, line_broken=3 |
| b2_paper_full_set | 6 | 17% | -0.031 | -0.0092 | 0.0536 | — | censored=3, line_broken=3 |
| c_trail15 | 6 | 17% | +0.037 | +0.0110 | 0.0449 | 409% | censored=2, trailing=4 |
| c_trail30 | 6 | 17% | -0.017 | -0.0050 | 0.0609 | — | censored=4, trailing=2 |
| c_trail50 | 6 | 17% | -0.017 | -0.0051 | 0.0610 | — | censored=6 |
| d_arm+25%_trail30 | 6 | 17% | -0.017 | -0.0051 | 0.0610 | — | censored=6 |
| d_arm+50%_trail30 | 6 | 17% | -0.017 | -0.0051 | 0.0610 | — | censored=6 |
| d_arm+100%_trail30 | 6 | 17% | -0.017 | -0.0051 | 0.0610 | — | censored=6 |
| d_arm+25%_trail15 | 6 | 17% | -0.017 | -0.0051 | 0.0610 | — | censored=6 |
| d_arm+50%_trail15 | 6 | 17% | -0.017 | -0.0051 | 0.0610 | — | censored=6 |
| d_tp+25%_else_trail30 | 6 | 17% | -0.149 | -0.0447 | 0.0609 | — | censored=3, target=1, trailing=2 |
| d_tp+50%_else_trail30 | 6 | 17% | -0.101 | -0.0302 | 0.0609 | — | censored=3, target=1, trailing=2 |
| d_tp+100%_else_trail30 | 6 | 17% | -0.032 | -0.0096 | 0.0609 | — | censored=3, target=1, trailing=2 |
| e_time2m | 6 | 17% | -0.129 | -0.0388 | 0.0549 | — | time_stop=6 |
| e_time5m | 6 | 17% | -0.070 | -0.0209 | 0.0518 | — | time_stop=6 |
| e_time15m | 6 | 17% | -0.011 | -0.0033 | 0.0592 | — | censored=1, time_stop=5 |
| e_time30m | 6 | 17% | -0.017 | -0.0051 | 0.0610 | — | censored=6 |
| f_first_creator_sell | 6 | 17% | -0.017 | -0.0051 | 0.0610 | — | censored=6 |
| f2_creator_sell_incl_15s_net_seller | 6 | 17% | -0.017 | -0.0051 | 0.0610 | — | censored=6 |
| g_tp30_or_trail20_or_5m | 6 | 17% | -0.121 | -0.0362 | 0.0524 | — | target=1, time_stop=1, trailing=4 |
| g2_tp30_or_trail20_or_2m | 6 | 17% | -0.121 | -0.0362 | 0.0524 | — | target=1, time_stop=1, trailing=4 |
| g3_tp50_or_trail20_or_5m | 6 | 17% | -0.073 | -0.0218 | 0.0524 | — | target=1, time_stop=1, trailing=4 |
| g4_tp30_or_trail15_or_5m | 6 | 17% | -0.096 | -0.0287 | 0.0449 | — | target=1, time_stop=1, trailing=4 |
| g5_tp30_or_trail15_or_2m | 6 | 17% | -0.095 | -0.0286 | 0.0448 | — | target=1, time_stop=1, trailing=4 |
| h_tp100_or_trail30_or_5m | 6 | 17% | -0.070 | -0.0209 | 0.0518 | — | time_stop=5, trailing=1 |
| h2_tp100_or_trail30_or_15m | 6 | 17% | -0.026 | -0.0079 | 0.0592 | — | target=1, time_stop=4, trailing=1 |
| h3_tp100_or_trail30_or_30m | 6 | 17% | -0.032 | -0.0096 | 0.0609 | — | censored=3, target=1, trailing=2 |
| h4_tp300_or_trail30_or_30m | 6 | 17% | -0.017 | -0.0050 | 0.0609 | — | censored=4, trailing=2 |

## flow_v2/8
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 5 | 20% | +0.001 | +0.0004 | 0.0428 | 8756% | line_broken=3, time_stop=2 |
| a2_actual_exit_mcap_fee1.25 | 5 | 20% | +0.014 | +0.0036 | 0.0408 | 978% | line_broken=3, time_stop=2 |
| b_line_broken(2) | 5 | 20% | +0.029 | +0.0074 | 0.0370 | 529% | censored=2, line_broken=3 |
| b2_paper_full_set | 5 | 20% | +0.029 | +0.0074 | 0.0370 | 529% | censored=2, line_broken=3 |
| c_trail15 | 5 | 20% | +0.086 | +0.0214 | 0.0345 | 211% | censored=2, trailing=3 |
| c_trail30 | 5 | 20% | +0.046 | +0.0115 | 0.0444 | 373% | censored=4, trailing=1 |
| c_trail50 | 5 | 20% | +0.046 | +0.0115 | 0.0444 | 375% | censored=5 |
| d_arm+25%_trail30 | 5 | 20% | +0.046 | +0.0115 | 0.0444 | 375% | censored=5 |
| d_arm+50%_trail30 | 5 | 20% | +0.046 | +0.0115 | 0.0444 | 375% | censored=5 |
| d_arm+100%_trail30 | 5 | 20% | +0.046 | +0.0115 | 0.0444 | 375% | censored=5 |
| d_arm+25%_trail15 | 5 | 20% | +0.046 | +0.0115 | 0.0444 | 375% | censored=5 |
| d_arm+50%_trail15 | 5 | 20% | +0.046 | +0.0115 | 0.0444 | 375% | censored=5 |
| d_tp+25%_else_trail30 | 5 | 20% | -0.113 | -0.0282 | 0.0444 | — | censored=3, target=1, trailing=1 |
| d_tp+50%_else_trail30 | 5 | 20% | -0.055 | -0.0137 | 0.0444 | — | censored=3, target=1, trailing=1 |
| d_tp+100%_else_trail30 | 5 | 20% | +0.028 | +0.0069 | 0.0444 | 558% | censored=3, target=1, trailing=1 |
| e_time2m | 5 | 20% | -0.096 | -0.0240 | 0.0402 | — | time_stop=5 |
| e_time5m | 5 | 20% | -0.024 | -0.0061 | 0.0370 | — | time_stop=5 |
| e_time15m | 5 | 20% | +0.046 | +0.0115 | 0.0444 | 373% | censored=1, time_stop=4 |
| e_time30m | 5 | 20% | +0.046 | +0.0115 | 0.0444 | 375% | censored=5 |
| f_first_creator_sell | 5 | 20% | +0.046 | +0.0115 | 0.0444 | 375% | censored=5 |
| f2_creator_sell_incl_15s_net_seller | 5 | 20% | +0.046 | +0.0115 | 0.0444 | 375% | censored=5 |
| g_tp30_or_trail20_or_5m | 5 | 20% | -0.092 | -0.0231 | 0.0393 | — | target=1, time_stop=1, trailing=3 |
| g2_tp30_or_trail20_or_2m | 5 | 20% | -0.092 | -0.0231 | 0.0392 | — | target=1, time_stop=1, trailing=3 |
| g3_tp50_or_trail20_or_5m | 5 | 20% | -0.035 | -0.0087 | 0.0393 | — | target=1, time_stop=1, trailing=3 |
| g4_tp30_or_trail15_or_5m | 5 | 20% | -0.073 | -0.0183 | 0.0345 | — | target=1, time_stop=1, trailing=3 |
| g5_tp30_or_trail15_or_2m | 5 | 20% | -0.073 | -0.0182 | 0.0344 | — | target=1, time_stop=1, trailing=3 |
| h_tp100_or_trail30_or_5m | 5 | 20% | -0.024 | -0.0061 | 0.0370 | — | time_stop=4, trailing=1 |
| h2_tp100_or_trail30_or_15m | 5 | 20% | +0.028 | +0.0069 | 0.0444 | 558% | target=1, time_stop=3, trailing=1 |
| h3_tp100_or_trail30_or_30m | 5 | 20% | +0.028 | +0.0069 | 0.0444 | 558% | censored=3, target=1, trailing=1 |
| h4_tp300_or_trail30_or_30m | 5 | 20% | +0.046 | +0.0115 | 0.0444 | 373% | censored=4, trailing=1 |

## papel (5 sets)
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 58 | 40% | +0.066 | +0.1921 | 0.0936 | 108% | creator_dump=7, line_broken=41, time_stop=10 |
| a2_actual_exit_mcap_fee1.25 | 58 | 47% | +0.079 | +0.2294 | 0.0923 | 92% | creator_dump=7, line_broken=41, time_stop=10 |
| b_line_broken(2) | 58 | 47% | +0.079 | +0.2284 | 0.1067 | 93% | censored=13, line_broken=45 |
| b2_paper_full_set | 58 | 43% | +0.071 | +0.2052 | 0.1067 | 103% | censored=10, creator_dump=7, line_broken=41 |
| c_trail15 | 58 | 41% | +0.072 | +0.2090 | 0.1366 | 81% | censored=9, trailing=49 |
| c_trail30 | 58 | 38% | +0.021 | +0.0600 | 0.2483 | 546% | censored=28, trailing=30 |
| c_trail50 | 58 | 38% | +0.022 | +0.0626 | 0.2551 | 523% | censored=40, trailing=18 |
| d_arm+25%_trail30 | 58 | 38% | +0.025 | +0.0712 | 0.2213 | 460% | censored=42, trailing=16 |
| d_arm+50%_trail30 | 58 | 41% | +0.065 | +0.1872 | 0.2168 | 175% | censored=44, trailing=14 |
| d_arm+100%_trail30 | 58 | 38% | +0.055 | +0.1604 | 0.2553 | 204% | censored=52, trailing=6 |
| d_arm+25%_trail15 | 58 | 45% | +0.020 | +0.0571 | 0.1448 | 296% | censored=32, trailing=26 |
| d_arm+50%_trail15 | 58 | 45% | +0.045 | +0.1292 | 0.1838 | 165% | censored=34, trailing=24 |
| d_tp+25%_else_trail30 | 58 | 59% | +0.051 | +0.1471 | 0.0920 | 57% | censored=12, target=32, trailing=14 |
| d_tp+50%_else_trail30 | 58 | 52% | +0.102 | +0.2961 | 0.1448 | 32% | censored=12, target=28, trailing=18 |
| d_tp+100%_else_trail30 | 58 | 41% | +0.013 | +0.0377 | 0.1948 | 442% | censored=20, target=10, trailing=28 |
| e_time2m | 58 | 41% | -0.001 | -0.0023 | 0.0885 | — | time_stop=58 |
| e_time5m | 58 | 48% | +0.062 | +0.1787 | 0.1766 | 61% | time_stop=58 |
| e_time15m | 58 | 45% | +0.267 | +0.7741 | 0.1805 | 43% | censored=19, time_stop=39 |
| e_time30m | 58 | 38% | +0.052 | +0.1507 | 0.2553 | 217% | censored=56, time_stop=2 |
| f_first_creator_sell | 58 | 41% | +0.083 | +0.2393 | 0.2067 | 137% | censored=43, creator_sell=15 |
| f2_creator_sell_incl_15s_net_seller | 58 | 45% | +0.073 | +0.2126 | 0.1988 | 154% | censored=43, creator_sell=15 |
| g_tp30_or_trail20_or_5m | 58 | 55% | +0.077 | +0.2236 | 0.0510 | 37% | target=24, time_stop=17, trailing=17 |
| g2_tp30_or_trail20_or_2m | 58 | 45% | +0.013 | +0.0365 | 0.0628 | 184% | target=11, time_stop=30, trailing=17 |
| g3_tp50_or_trail20_or_5m | 58 | 52% | +0.113 | +0.3281 | 0.0510 | 29% | target=14, time_stop=25, trailing=19 |
| g4_tp30_or_trail15_or_5m | 58 | 52% | +0.061 | +0.1755 | 0.0649 | 47% | target=22, time_stop=13, trailing=23 |
| g5_tp30_or_trail15_or_2m | 58 | 45% | +0.014 | +0.0394 | 0.0649 | 171% | target=11, time_stop=27, trailing=20 |
| h_tp100_or_trail30_or_5m | 58 | 48% | +0.050 | +0.1455 | 0.1824 | 75% | time_stop=45, trailing=13 |
| h2_tp100_or_trail30_or_15m | 58 | 41% | +0.077 | +0.2219 | 0.1914 | 75% | censored=2, target=10, time_stop=24, trailing=22 |
| h3_tp100_or_trail30_or_30m | 58 | 41% | +0.013 | +0.0377 | 0.1948 | 442% | censored=20, target=10, trailing=28 |
| h4_tp300_or_trail30_or_30m | 58 | 38% | +0.018 | +0.0531 | 0.2483 | 605% | censored=26, target=2, trailing=30 |

## papel unico (mint@minuto)
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 30 | 40% | +0.058 | +0.0867 | 0.0468 | 208% | creator_dump=4, line_broken=21, time_stop=5 |
| a2_actual_exit_mcap_fee1.25 | 30 | 47% | +0.071 | +0.1058 | 0.0461 | 174% | creator_dump=4, line_broken=21, time_stop=5 |
| b_line_broken(2) | 30 | 47% | +0.073 | +0.1097 | 0.0533 | 168% | censored=7, line_broken=23 |
| b2_paper_full_set | 30 | 43% | +0.065 | +0.0981 | 0.0533 | 188% | censored=5, creator_dump=4, line_broken=21 |
| c_trail15 | 30 | 43% | +0.085 | +0.1273 | 0.0639 | 122% | censored=5, trailing=25 |
| c_trail30 | 30 | 40% | +0.029 | +0.0440 | 0.1176 | 578% | censored=14, trailing=16 |
| c_trail50 | 30 | 40% | +0.028 | +0.0425 | 0.1275 | 599% | censored=21, trailing=9 |
| d_arm+25%_trail30 | 30 | 40% | +0.031 | +0.0468 | 0.1084 | 544% | censored=22, trailing=8 |
| d_arm+50%_trail30 | 30 | 43% | +0.070 | +0.1048 | 0.1084 | 243% | censored=23, trailing=7 |
| d_arm+100%_trail30 | 30 | 40% | +0.061 | +0.0914 | 0.1276 | 279% | censored=27, trailing=3 |
| d_arm+25%_trail15 | 30 | 47% | +0.026 | +0.0397 | 0.0679 | 391% | censored=17, trailing=13 |
| d_arm+50%_trail15 | 30 | 47% | +0.051 | +0.0758 | 0.0919 | 252% | censored=18, trailing=12 |
| d_tp+25%_else_trail30 | 30 | 60% | +0.060 | +0.0902 | 0.0460 | 93% | censored=5, target=17, trailing=8 |
| d_tp+50%_else_trail30 | 30 | 53% | +0.110 | +0.1647 | 0.0679 | 58% | censored=5, target=15, trailing=10 |
| d_tp+100%_else_trail30 | 30 | 43% | +0.022 | +0.0328 | 0.0974 | 490% | censored=10, target=5, trailing=15 |
| e_time2m | 30 | 43% | +0.008 | +0.0114 | 0.0431 | 713% | time_stop=30 |
| e_time5m | 30 | 50% | +0.071 | +0.1065 | 0.0883 | 99% | time_stop=30 |
| e_time15m | 30 | 47% | +0.266 | +0.3985 | 0.0902 | 76% | censored=11, time_stop=19 |
| e_time30m | 30 | 40% | +0.058 | +0.0865 | 0.1276 | 294% | censored=29, time_stop=1 |
| f_first_creator_sell | 30 | 43% | +0.086 | +0.1295 | 0.0958 | 196% | censored=21, creator_sell=9 |
| f2_creator_sell_incl_15s_net_seller | 30 | 47% | +0.080 | +0.1201 | 0.0958 | 211% | censored=21, creator_sell=9 |
| g_tp30_or_trail20_or_5m | 30 | 57% | +0.089 | +0.1328 | 0.0261 | 62% | target=13, time_stop=8, trailing=9 |
| g2_tp30_or_trail20_or_2m | 30 | 47% | +0.019 | +0.0290 | 0.0296 | 219% | target=6, time_stop=15, trailing=9 |
| g3_tp50_or_trail20_or_5m | 30 | 53% | +0.123 | +0.1850 | 0.0261 | 50% | target=8, time_stop=12, trailing=10 |
| g4_tp30_or_trail15_or_5m | 30 | 53% | +0.075 | +0.1132 | 0.0325 | 72% | target=12, time_stop=6, trailing=12 |
| g5_tp30_or_trail15_or_2m | 30 | 47% | +0.020 | +0.0305 | 0.0325 | 208% | target=6, time_stop=13, trailing=11 |
| h_tp100_or_trail30_or_5m | 30 | 50% | +0.061 | +0.0912 | 0.0912 | 116% | time_stop=23, trailing=7 |
| h2_tp100_or_trail30_or_15m | 30 | 43% | +0.083 | +0.1249 | 0.0957 | 129% | censored=2, target=5, time_stop=11, trailing=12 |
| h3_tp100_or_trail30_or_30m | 30 | 43% | +0.022 | +0.0328 | 0.0974 | 490% | censored=10, target=5, trailing=15 |
| h4_tp300_or_trail30_or_30m | 30 | 40% | +0.027 | +0.0405 | 0.1176 | 620% | censored=13, target=1, trailing=16 |

## as posicoes reais, aposta a aposta (PnL a 0,05 SOL, taxas 1,25 %)
| mint | cobertura | a_actual_recorded | b_line_broken(2) | c_trail15 | c_trail30 | e_time2m | e_time5m | f_first_creator_sell | g_tp30_or_trail20_or_5m | g5_tp30_or_trail15_or_2m |
|---|---|---|---|---|---|---|---|---|---|---|
| 7s4dKmpv | 214s | -0.0093 (creator_dump, 48s) | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie |
| 63NPcW9q | 94s | -0.0035 (creator_dump, 52s) | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie |
| CCLstvwa | 394s | -0.0071 (trailing, 396s) | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie |
| 2hhJXPy3 | 1557s | -0.0176 (time_stop, 1800s) | -0.0166 (censored, 1557s) | -0.0104 (trailing, 20s) | -0.0165 (trailing, 1366s) | -0.0148 (time_stop, 132s) | -0.0148 (time_stop, 307s) | -0.0166 (censored, 1557s) | -0.0131 (trailing, 52s) | -0.0104 (trailing, 20s) |
| Dy9YAbcL | 514s | -0.0059 (creator_dump, 514s) | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie |
| GdZ5hSdz | 179s | -0.0038 (creator_dump, 86s) | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie |
| 6zdT1MxC | 417s | +0.0329 (creator_dump, 117s) | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie |
| rYJYP8jV | 157s | -0.0040 (creator_dump, 45s) | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie |
| M3kpWCVA | 1586s | -0.0122 (time_stop, 1804s) | -0.0074 (line_broken, 31s) | -0.0089 (trailing, 63s) | -0.0110 (censored, 1586s) | -0.0105 (time_stop, 129s) | -0.0040 (time_stop, 308s) | -0.0110 (censored, 1586s) | -0.0040 (time_stop, 308s) | -0.0089 (trailing, 63s) |
| 8DqtPVgJ | 207s | -0.0025 (creator_dump, 33s) | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie |
| 4c3rRxkp | 1738s | -0.0029 (time_stop, 1804s) | -0.0014 (line_broken, 124s) | -0.0014 (censored, 1738s) | -0.0014 (censored, 1738s) | -0.0014 (time_stop, 124s) | -0.0014 (time_stop, 315s) | -0.0014 (censored, 1738s) | -0.0014 (time_stop, 315s) | -0.0014 (time_stop, 124s) |
| ADxEynfQ | 212s | -0.0383 (trailing, 43s) | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie |

## top-3 contribuintes (papel unico)
- a2_actual_exit_mcap_fee1.25: soma +0.1058; top3 = H88Srjvu +0.0719 (line_broken, 0s); EuS3oJQ9 +0.0682 (line_broken, 0s); HTqzwV4F +0.0444 (line_broken, 0s)
- c_trail15: soma +0.1273; top3 = 2FA3TvPu +0.0565 (censored, 812s); HTqzwV4F +0.0559 (censored, 831s); H88Srjvu +0.0430 (trailing, 414s)
- c_trail30: soma +0.0440; top3 = H88Srjvu +0.1297 (censored, 1323s); EuS3oJQ9 +0.0682 (censored, 618s); 2FA3TvPu +0.0565 (censored, 812s)
- d_tp+100%_else_trail30: soma +0.0328; top3 = EuS3oJQ9 +0.0571 (target, 363s); 9X6JGssV +0.0523 (target, 706s); 2FA3TvPu +0.0515 (target, 602s)
- e_time5m: soma +0.1065; top3 = 2FA3TvPu +0.0371 (time_stop, 310s); PPBPATwe +0.0347 (time_stop, 704s); H88Srjvu +0.0336 (time_stop, 302s)

## ranking (soma SOL, top3 < 50 %)
- papel (5 sets): melhor com top3<50%: e_time15m (+0.7741, top3 43%), g3_tp50_or_trail20_or_5m (+0.3281, top3 29%), d_tp+50%_else_trail30 (+0.2961, top3 32%), g_tp30_or_trail20_or_5m (+0.2236, top3 37%) | melhor absoluta: e_time15m (+0.7741, top3 43%)
- papel unico (mint@minuto): melhor com top3<50%: nenhuma | melhor absoluta: e_time15m (+0.3985, top3 76%)
- operator/5 real: melhor com top3<50%: nenhuma | melhor absoluta: g_tp30_or_trail20_or_5m (-0.0185, top3 nan%)
- operator/5: melhor com top3<50%: nenhuma | melhor absoluta: g_tp30_or_trail20_or_5m (-0.0163, top3 nan%)
- flow_v2/5: melhor com top3<50%: g3_tp50_or_trail20_or_5m (+0.1680, top3 47%), g_tp30_or_trail20_or_5m (+0.1302, top3 45%) | melhor absoluta: e_time15m (+0.3895, top3 78%)
- flow_v2/2: melhor com top3<50%: g3_tp50_or_trail20_or_5m (+0.2068, top3 43%), d_tp+50%_else_trail30 (+0.1949, top3 49%), g_tp30_or_trail20_or_5m (+0.1690, top3 49%) | melhor absoluta: e_time15m (+0.4017, top3 76%)
- flow_v2/6: melhor com top3<50%: nenhuma | melhor absoluta: c_trail15 (+0.0110, top3 409%)
- flow_v2/8: melhor com top3<50%: nenhuma | melhor absoluta: c_trail15 (+0.0214, top3 211%)

## delta pareado por aposta (regra - saida registrada a 1,25 %), modo=hold

### papel unico (mint@minuto) (n=30)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 10 | 3 | 17 | +0.0000 | +0.0039 | 66% | 0.09 |
| b2_paper_full_set | 8 | 4 | 18 | +0.0000 | -0.0077 | 82% | 0.39 |
| c_trail15 | 16 | 14 | 0 | +0.0017 | +0.0215 | 44% | 0.86 |
| c_trail30 | 16 | 10 | 4 | +0.0001 | -0.0618 | 54% | 0.33 |
| c_trail50 | 13 | 11 | 6 | +0.0000 | -0.0633 | 52% | 0.84 |
| d_arm+25%_trail30 | 12 | 12 | 6 | +0.0000 | -0.0590 | 56% | 1.00 |
| d_arm+50%_trail30 | 13 | 11 | 6 | +0.0000 | -0.0010 | 50% | 0.84 |
| d_arm+100%_trail30 | 13 | 11 | 6 | +0.0000 | -0.0145 | 46% | 0.84 |
| d_arm+25%_trail15 | 12 | 13 | 5 | +0.0000 | -0.0661 | 55% | 1.00 |
| d_arm+50%_trail15 | 13 | 12 | 5 | +0.0000 | -0.0300 | 53% | 1.00 |
| d_tp+25%_else_trail30 | 16 | 9 | 5 | +0.0001 | -0.0156 | 52% | 0.23 |
| d_tp+50%_else_trail30 | 18 | 8 | 4 | +0.0005 | +0.0589 | 42% | 0.08 |
| d_tp+100%_else_trail30 | 16 | 11 | 3 | +0.0001 | -0.0730 | 55% | 0.44 |
| e_time2m | 20 | 10 | 0 | +0.0033 | -0.0944 | 38% | 0.10 |
| e_time5m | 18 | 12 | 0 | +0.0014 | +0.0006 | 40% | 0.36 |
| e_time15m | 18 | 7 | 5 | +0.0017 | +0.2926 | 49% | 0.04 |
| e_time30m | 13 | 11 | 6 | +0.0000 | -0.0193 | 53% | 0.84 |
| f_first_creator_sell | 13 | 10 | 7 | +0.0000 | +0.0237 | 52% | 0.68 |
| f2_creator_sell_incl_15s_net_seller | 12 | 9 | 9 | +0.0000 | +0.0143 | 56% | 0.66 |
| g_tp30_or_trail20_or_5m | 16 | 12 | 2 | +0.0023 | +0.0270 | 40% | 0.57 |
| g2_tp30_or_trail20_or_2m | 19 | 9 | 2 | +0.0031 | -0.0768 | 37% | 0.09 |
| g3_tp50_or_trail20_or_5m | 17 | 12 | 1 | +0.0031 | +0.0792 | 38% | 0.46 |
| g4_tp30_or_trail15_or_5m | 15 | 13 | 2 | +0.0009 | +0.0074 | 39% | 0.85 |
| g5_tp30_or_trail15_or_2m | 18 | 10 | 2 | +0.0029 | -0.0753 | 36% | 0.18 |
| h_tp100_or_trail30_or_5m | 18 | 12 | 0 | +0.0006 | -0.0146 | 45% | 0.36 |
| h2_tp100_or_trail30_or_15m | 17 | 10 | 3 | +0.0002 | +0.0191 | 48% | 0.25 |
| h3_tp100_or_trail30_or_30m | 16 | 11 | 3 | +0.0001 | -0.0730 | 55% | 0.44 |
| h4_tp300_or_trail30_or_30m | 16 | 10 | 4 | +0.0001 | -0.0653 | 53% | 0.33 |

### operator/5 real (n=3)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 3 | 0 | 0 | +0.0002 | +0.0040 | 100% | 0.25 |
| b2_paper_full_set | 3 | 0 | 0 | +0.0002 | +0.0040 | 100% | 0.25 |
| c_trail15 | 3 | 0 | 0 | +0.0022 | +0.0086 | 100% | 0.25 |
| c_trail30 | 3 | 0 | 0 | +0.0001 | +0.0004 | 100% | 0.25 |
| c_trail50 | 3 | 0 | 0 | +0.0001 | +0.0003 | 100% | 0.25 |
| d_arm+25%_trail30 | 3 | 0 | 0 | +0.0001 | +0.0003 | 100% | 0.25 |
| d_arm+50%_trail30 | 3 | 0 | 0 | +0.0001 | +0.0003 | 100% | 0.25 |
| d_arm+100%_trail30 | 3 | 0 | 0 | +0.0001 | +0.0003 | 100% | 0.25 |
| d_arm+25%_trail15 | 3 | 0 | 0 | +0.0001 | +0.0003 | 100% | 0.25 |
| d_arm+50%_trail15 | 3 | 0 | 0 | +0.0001 | +0.0003 | 100% | 0.25 |
| d_tp+25%_else_trail30 | 3 | 0 | 0 | +0.0001 | +0.0004 | 100% | 0.25 |
| d_tp+50%_else_trail30 | 3 | 0 | 0 | +0.0001 | +0.0004 | 100% | 0.25 |
| d_tp+100%_else_trail30 | 3 | 0 | 0 | +0.0001 | +0.0004 | 100% | 0.25 |
| e_time2m | 3 | 0 | 0 | +0.0006 | +0.0027 | 100% | 0.25 |
| e_time5m | 3 | 0 | 0 | +0.0019 | +0.0092 | 100% | 0.25 |
| e_time15m | 3 | 0 | 0 | +0.0002 | +0.0021 | 100% | 0.25 |
| e_time30m | 3 | 0 | 0 | +0.0001 | +0.0003 | 100% | 0.25 |
| f_first_creator_sell | 3 | 0 | 0 | +0.0001 | +0.0003 | 100% | 0.25 |
| f2_creator_sell_incl_15s_net_seller | 3 | 0 | 0 | +0.0001 | +0.0003 | 100% | 0.25 |
| g_tp30_or_trail20_or_5m | 3 | 0 | 0 | +0.0035 | +0.0109 | 100% | 0.25 |
| g2_tp30_or_trail20_or_2m | 3 | 0 | 0 | +0.0006 | +0.0043 | 100% | 0.25 |
| g3_tp50_or_trail20_or_5m | 3 | 0 | 0 | +0.0035 | +0.0109 | 100% | 0.25 |
| g4_tp30_or_trail15_or_5m | 3 | 0 | 0 | +0.0022 | +0.0086 | 100% | 0.25 |
| g5_tp30_or_trail15_or_2m | 3 | 0 | 0 | +0.0022 | +0.0087 | 100% | 0.25 |
| h_tp100_or_trail30_or_5m | 3 | 0 | 0 | +0.0019 | +0.0092 | 100% | 0.25 |
| h2_tp100_or_trail30_or_15m | 3 | 0 | 0 | +0.0002 | +0.0021 | 100% | 0.25 |
| h3_tp100_or_trail30_or_30m | 3 | 0 | 0 | +0.0001 | +0.0004 | 100% | 0.25 |
| h4_tp300_or_trail30_or_30m | 3 | 0 | 0 | +0.0001 | +0.0004 | 100% | 0.25 |

### operator/5 (n=3)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 2 | 0 | 1 | +0.0000 | +0.0001 | 100% | 0.50 |
| b2_paper_full_set | 2 | 0 | 1 | +0.0000 | +0.0001 | 100% | 0.50 |
| c_trail15 | 1 | 2 | 0 | -0.0000 | +0.0026 | 100% | 1.00 |
| c_trail30 | 1 | 2 | 0 | -0.0000 | -0.0037 | 100% | 1.00 |
| c_trail50 | 1 | 2 | 0 | -0.0000 | -0.0038 | 100% | 1.00 |
| d_arm+25%_trail30 | 1 | 2 | 0 | -0.0000 | -0.0038 | 100% | 1.00 |
| d_arm+50%_trail30 | 1 | 2 | 0 | -0.0000 | -0.0038 | 100% | 1.00 |
| d_arm+100%_trail30 | 1 | 2 | 0 | -0.0000 | -0.0038 | 100% | 1.00 |
| d_arm+25%_trail15 | 1 | 2 | 0 | -0.0000 | -0.0038 | 100% | 1.00 |
| d_arm+50%_trail15 | 1 | 2 | 0 | -0.0000 | -0.0038 | 100% | 1.00 |
| d_tp+25%_else_trail30 | 1 | 2 | 0 | -0.0000 | -0.0037 | 100% | 1.00 |
| d_tp+50%_else_trail30 | 1 | 2 | 0 | -0.0000 | -0.0037 | 100% | 1.00 |
| d_tp+100%_else_trail30 | 1 | 2 | 0 | -0.0000 | -0.0037 | 100% | 1.00 |
| e_time2m | 1 | 1 | 1 | +0.0000 | -0.0014 | 100% | 1.00 |
| e_time5m | 2 | 1 | 0 | +0.0019 | +0.0054 | 100% | 1.00 |
| e_time15m | 1 | 2 | 0 | -0.0000 | -0.0020 | 100% | 1.00 |
| e_time30m | 1 | 2 | 0 | -0.0000 | -0.0038 | 100% | 1.00 |
| f_first_creator_sell | 1 | 2 | 0 | -0.0000 | -0.0038 | 100% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 1 | 2 | 0 | -0.0000 | -0.0038 | 100% | 1.00 |
| g_tp30_or_trail20_or_5m | 2 | 1 | 0 | +0.0035 | +0.0071 | 100% | 1.00 |
| g2_tp30_or_trail20_or_2m | 1 | 1 | 1 | +0.0000 | +0.0002 | 100% | 1.00 |
| g3_tp50_or_trail20_or_5m | 2 | 1 | 0 | +0.0035 | +0.0071 | 100% | 1.00 |
| g4_tp30_or_trail15_or_5m | 1 | 2 | 0 | -0.0000 | +0.0026 | 100% | 1.00 |
| g5_tp30_or_trail15_or_2m | 1 | 1 | 1 | +0.0000 | +0.0030 | 100% | 1.00 |
| h_tp100_or_trail30_or_5m | 2 | 1 | 0 | +0.0019 | +0.0054 | 100% | 1.00 |
| h2_tp100_or_trail30_or_15m | 1 | 2 | 0 | -0.0000 | -0.0020 | 100% | 1.00 |
| h3_tp100_or_trail30_or_30m | 1 | 2 | 0 | -0.0000 | -0.0037 | 100% | 1.00 |
| h4_tp300_or_trail30_or_30m | 1 | 2 | 0 | -0.0000 | -0.0037 | 100% | 1.00 |

### flow_v2/5 (n=20)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 4 | 3 | 13 | +0.0000 | -0.0088 | 97% | 1.00 |
| b2_paper_full_set | 2 | 4 | 14 | +0.0000 | -0.0204 | 100% | 0.69 |
| c_trail15 | 8 | 12 | 0 | -0.0010 | -0.0623 | 61% | 0.50 |
| c_trail30 | 9 | 8 | 3 | +0.0000 | -0.1118 | 67% | 1.00 |
| c_trail50 | 9 | 8 | 3 | +0.0000 | -0.1075 | 62% | 1.00 |
| d_arm+25%_trail30 | 8 | 9 | 3 | +0.0000 | -0.1032 | 68% | 1.00 |
| d_arm+50%_trail30 | 9 | 8 | 3 | +0.0000 | -0.0452 | 59% | 1.00 |
| d_arm+100%_trail30 | 9 | 8 | 3 | +0.0000 | -0.0587 | 55% | 1.00 |
| d_arm+25%_trail15 | 8 | 10 | 2 | -0.0001 | -0.1103 | 67% | 0.81 |
| d_arm+50%_trail15 | 9 | 9 | 2 | +0.0000 | -0.0742 | 64% | 1.00 |
| d_tp+25%_else_trail30 | 10 | 6 | 4 | +0.0008 | -0.0312 | 52% | 0.45 |
| d_tp+50%_else_trail30 | 12 | 5 | 3 | +0.0028 | +0.0289 | 45% | 0.14 |
| d_tp+100%_else_trail30 | 9 | 9 | 2 | +0.0000 | -0.1183 | 64% | 1.00 |
| e_time2m | 12 | 8 | 0 | +0.0040 | -0.1083 | 53% | 0.50 |
| e_time5m | 11 | 9 | 0 | +0.0038 | -0.0470 | 45% | 0.82 |
| e_time15m | 13 | 4 | 3 | +0.0073 | +0.2462 | 55% | 0.05 |
| e_time30m | 9 | 8 | 3 | +0.0000 | -0.0635 | 62% | 1.00 |
| f_first_creator_sell | 9 | 7 | 4 | +0.0000 | -0.0178 | 62% | 0.80 |
| f2_creator_sell_incl_15s_net_seller | 8 | 6 | 6 | +0.0000 | -0.0352 | 68% | 0.79 |
| g_tp30_or_trail20_or_5m | 9 | 9 | 2 | +0.0000 | -0.0131 | 45% | 1.00 |
| g2_tp30_or_trail20_or_2m | 11 | 7 | 2 | +0.0023 | -0.0897 | 52% | 0.48 |
| g3_tp50_or_trail20_or_5m | 10 | 9 | 1 | +0.0054 | +0.0246 | 44% | 1.00 |
| g4_tp30_or_trail15_or_5m | 8 | 10 | 2 | -0.0000 | -0.0420 | 46% | 0.81 |
| g5_tp30_or_trail15_or_2m | 10 | 8 | 2 | +0.0003 | -0.0958 | 55% | 0.81 |
| h_tp100_or_trail30_or_5m | 10 | 10 | 0 | +0.0004 | -0.0651 | 49% | 1.00 |
| h2_tp100_or_trail30_or_15m | 10 | 8 | 2 | +0.0001 | -0.0279 | 55% | 0.81 |
| h3_tp100_or_trail30_or_30m | 9 | 9 | 2 | +0.0000 | -0.1183 | 64% | 1.00 |
| h4_tp300_or_trail30_or_30m | 9 | 8 | 3 | +0.0000 | -0.1153 | 66% | 1.00 |

### flow_v2/2 (n=24)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 7 | 3 | 14 | +0.0000 | +0.0001 | 74% | 0.34 |
| b2_paper_full_set | 5 | 4 | 15 | +0.0000 | -0.0115 | 95% | 1.00 |
| c_trail15 | 12 | 12 | 0 | +0.0007 | -0.0026 | 49% | 1.00 |
| c_trail30 | 13 | 8 | 3 | +0.0009 | -0.0699 | 57% | 0.38 |
| c_trail50 | 11 | 9 | 4 | +0.0000 | -0.0712 | 54% | 0.82 |
| d_arm+25%_trail30 | 10 | 10 | 4 | +0.0000 | -0.0670 | 59% | 1.00 |
| d_arm+50%_trail30 | 11 | 9 | 4 | +0.0000 | -0.0090 | 52% | 0.82 |
| d_arm+100%_trail30 | 11 | 9 | 4 | +0.0000 | -0.0224 | 48% | 0.82 |
| d_arm+25%_trail15 | 10 | 11 | 3 | +0.0000 | -0.0740 | 58% | 1.00 |
| d_arm+50%_trail15 | 11 | 10 | 3 | +0.0000 | -0.0380 | 56% | 1.00 |
| d_tp+25%_else_trail30 | 14 | 6 | 4 | +0.0016 | +0.0160 | 52% | 0.12 |
| d_tp+50%_else_trail30 | 16 | 5 | 3 | +0.0029 | +0.0760 | 42% | 0.03 |
| d_tp+100%_else_trail30 | 13 | 9 | 2 | +0.0009 | -0.0764 | 57% | 0.52 |
| e_time2m | 16 | 8 | 0 | +0.0044 | -0.0687 | 39% | 0.15 |
| e_time5m | 14 | 10 | 0 | +0.0057 | +0.0085 | 41% | 0.54 |
| e_time15m | 15 | 5 | 4 | +0.0029 | +0.2829 | 50% | 0.04 |
| e_time30m | 11 | 9 | 4 | +0.0000 | -0.0272 | 55% | 0.82 |
| f_first_creator_sell | 11 | 8 | 5 | +0.0000 | +0.0158 | 54% | 0.65 |
| f2_creator_sell_incl_15s_net_seller | 10 | 7 | 7 | +0.0000 | +0.0064 | 59% | 0.63 |
| g_tp30_or_trail20_or_5m | 13 | 9 | 2 | +0.0049 | +0.0501 | 42% | 0.52 |
| g2_tp30_or_trail20_or_2m | 15 | 7 | 2 | +0.0044 | -0.0536 | 39% | 0.13 |
| g3_tp50_or_trail20_or_5m | 14 | 9 | 1 | +0.0081 | +0.0879 | 39% | 0.40 |
| g4_tp30_or_trail15_or_5m | 12 | 10 | 2 | +0.0023 | +0.0230 | 42% | 0.83 |
| g5_tp30_or_trail15_or_2m | 14 | 8 | 2 | +0.0040 | -0.0597 | 40% | 0.29 |
| h_tp100_or_trail30_or_5m | 14 | 10 | 0 | +0.0024 | -0.0068 | 46% | 0.54 |
| h2_tp100_or_trail30_or_15m | 14 | 8 | 2 | +0.0009 | +0.0140 | 49% | 0.29 |
| h3_tp100_or_trail30_or_30m | 13 | 9 | 2 | +0.0009 | -0.0764 | 57% | 0.52 |
| h4_tp300_or_trail30_or_30m | 13 | 8 | 3 | +0.0009 | -0.0734 | 56% | 0.38 |

### flow_v2/6 (n=6)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 3 | 0 | 3 | +0.0000 | +0.0038 | 100% | 0.25 |
| b2_paper_full_set | 3 | 0 | 3 | +0.0000 | +0.0038 | 100% | 0.25 |
| c_trail15 | 4 | 2 | 0 | +0.0039 | +0.0241 | 93% | 0.69 |
| c_trail30 | 3 | 2 | 1 | +0.0000 | +0.0081 | 100% | 1.00 |
| c_trail50 | 2 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| d_arm+25%_trail30 | 2 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| d_arm+50%_trail30 | 2 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| d_arm+100%_trail30 | 2 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| d_arm+25%_trail15 | 2 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| d_arm+50%_trail15 | 2 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| d_tp+25%_else_trail30 | 2 | 3 | 1 | -0.0000 | -0.0316 | 100% | 1.00 |
| d_tp+50%_else_trail30 | 2 | 3 | 1 | -0.0000 | -0.0172 | 100% | 1.00 |
| d_tp+100%_else_trail30 | 3 | 2 | 1 | +0.0000 | +0.0034 | 100% | 1.00 |
| e_time2m | 4 | 2 | 0 | +0.0005 | -0.0257 | 100% | 0.69 |
| e_time5m | 4 | 2 | 0 | +0.0002 | -0.0078 | 99% | 0.69 |
| e_time15m | 3 | 2 | 1 | +0.0000 | +0.0098 | 100% | 1.00 |
| e_time30m | 2 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| f_first_creator_sell | 2 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 2 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| g_tp30_or_trail20_or_5m | 3 | 3 | 0 | +0.0009 | -0.0232 | 100% | 1.00 |
| g2_tp30_or_trail20_or_2m | 4 | 2 | 0 | +0.0010 | -0.0231 | 100% | 0.69 |
| g3_tp50_or_trail20_or_5m | 3 | 3 | 0 | +0.0009 | -0.0087 | 100% | 1.00 |
| g4_tp30_or_trail15_or_5m | 3 | 3 | 0 | +0.0009 | -0.0156 | 100% | 1.00 |
| g5_tp30_or_trail15_or_2m | 4 | 2 | 0 | +0.0010 | -0.0156 | 100% | 0.69 |
| h_tp100_or_trail30_or_5m | 4 | 2 | 0 | +0.0002 | -0.0078 | 99% | 0.69 |
| h2_tp100_or_trail30_or_15m | 3 | 2 | 1 | +0.0000 | +0.0051 | 100% | 1.00 |
| h3_tp100_or_trail30_or_30m | 3 | 2 | 1 | +0.0000 | +0.0034 | 100% | 1.00 |
| h4_tp300_or_trail30_or_30m | 3 | 2 | 1 | +0.0000 | +0.0081 | 100% | 1.00 |

### flow_v2/8 (n=5)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 2 | 0 | 3 | +0.0000 | +0.0038 | 100% | 0.50 |
| b2_paper_full_set | 2 | 0 | 3 | +0.0000 | +0.0038 | 100% | 0.50 |
| c_trail15 | 3 | 2 | 0 | +0.0019 | +0.0178 | 100% | 1.00 |
| c_trail30 | 2 | 2 | 1 | +0.0000 | +0.0079 | 100% | 1.00 |
| c_trail50 | 1 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| d_arm+25%_trail30 | 1 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| d_arm+50%_trail30 | 1 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| d_arm+100%_trail30 | 1 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| d_arm+25%_trail15 | 1 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| d_arm+50%_trail15 | 1 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| d_tp+25%_else_trail30 | 1 | 3 | 1 | -0.0000 | -0.0318 | 100% | 0.62 |
| d_tp+50%_else_trail30 | 1 | 3 | 1 | -0.0000 | -0.0173 | 100% | 0.62 |
| d_tp+100%_else_trail30 | 2 | 2 | 1 | +0.0000 | +0.0033 | 100% | 1.00 |
| e_time2m | 3 | 2 | 0 | +0.0000 | -0.0276 | 100% | 1.00 |
| e_time5m | 3 | 2 | 0 | +0.0001 | -0.0097 | 100% | 1.00 |
| e_time15m | 2 | 2 | 1 | +0.0000 | +0.0079 | 100% | 1.00 |
| e_time30m | 1 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| f_first_creator_sell | 1 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 1 | 2 | 2 | +0.0000 | +0.0079 | 100% | 1.00 |
| g_tp30_or_trail20_or_5m | 2 | 3 | 0 | -0.0000 | -0.0267 | 100% | 1.00 |
| g2_tp30_or_trail20_or_2m | 3 | 2 | 0 | +0.0000 | -0.0267 | 100% | 1.00 |
| g3_tp50_or_trail20_or_5m | 2 | 3 | 0 | -0.0000 | -0.0123 | 100% | 1.00 |
| g4_tp30_or_trail15_or_5m | 2 | 3 | 0 | -0.0000 | -0.0219 | 100% | 1.00 |
| g5_tp30_or_trail15_or_2m | 3 | 2 | 0 | +0.0000 | -0.0218 | 100% | 1.00 |
| h_tp100_or_trail30_or_5m | 3 | 2 | 0 | +0.0001 | -0.0097 | 100% | 1.00 |
| h2_tp100_or_trail30_or_15m | 2 | 2 | 1 | +0.0000 | +0.0033 | 100% | 1.00 |
| h3_tp100_or_trail30_or_30m | 2 | 2 | 1 | +0.0000 | +0.0033 | 100% | 1.00 |
| h4_tp300_or_trail30_or_30m | 2 | 2 | 1 | +0.0000 | +0.0079 | 100% | 1.00 |
