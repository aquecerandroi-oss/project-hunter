## cobertura
modo=hold min_cover=120s taxa=1.25% por perna
| set | apostas | elegiveis | sem serie | cobertura mediana (s) | hold mediano (s) |
|---|---|---|---|---|---|
| operator/5 real | 12 | 11 | 0 | 304 | 102 |
| operator/5 | 19 | 17 | 0 | 298 | 73 |
| flow_v2/5 | 139 | 111 | 1 | 194 | 76 |
| flow_v2/2 | 165 | 127 | 1 | 183 | 76 |
| flow_v2/6 | 25 | 21 | 0 | 222 | 79 |
| flow_v2/8 | 31 | 22 | 0 | 199 | 76 |

## operator/5 real
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 11 | 9% | -0.128 | -0.0706 | 0.0706 | — | creator_dump=6, time_stop=3, trailing=2 |
| a2_actual_exit_mcap_fee1.25 | 11 | 9% | -0.102 | -0.0563 | 0.0563 | — | creator_dump=6, time_stop=3, trailing=2 |
| b_line_broken(2) | 11 | 27% | +0.002 | +0.0012 | 0.0492 | 7668% | censored=5, line_broken=6 |
| b2_paper_full_set | 11 | 18% | -0.105 | -0.0575 | 0.0575 | — | censored=1, creator_dump=5, line_broken=4, max_loss=1 |
| c_trail15 | 11 | 18% | -0.029 | -0.0157 | 0.0625 | — | censored=4, trailing=7 |
| c_trail30 | 11 | 18% | -0.030 | -0.0164 | 0.0529 | — | censored=7, trailing=4 |
| c_trail50 | 11 | 18% | -0.030 | -0.0164 | 0.0529 | — | censored=10, trailing=1 |
| d_arm+25%_trail30 | 11 | 18% | -0.030 | -0.0165 | 0.0529 | — | censored=9, trailing=2 |
| d_arm+50%_trail30 | 11 | 18% | -0.030 | -0.0164 | 0.0529 | — | censored=11 |
| d_arm+100%_trail30 | 11 | 18% | -0.030 | -0.0164 | 0.0529 | — | censored=11 |
| d_arm+25%_trail15 | 11 | 36% | -0.002 | -0.0008 | 0.0529 | — | censored=9, trailing=2 |
| d_arm+50%_trail15 | 11 | 18% | -0.030 | -0.0164 | 0.0529 | — | censored=11 |
| d_tp+25%_else_trail30 | 11 | 36% | -0.071 | -0.0389 | 0.0567 | — | censored=6, target=3, trailing=2 |
| d_tp+50%_else_trail30 | 11 | 18% | -0.102 | -0.0564 | 0.0564 | — | censored=6, target=1, trailing=4 |
| d_tp+100%_else_trail30 | 11 | 18% | -0.081 | -0.0448 | 0.0529 | — | censored=6, target=1, trailing=4 |
| e_time2m | 11 | 18% | -0.097 | -0.0532 | 0.0629 | — | time_stop=11 |
| e_time5m | 11 | 36% | +0.015 | +0.0084 | 0.0458 | 991% | censored=5, time_stop=6 |
| e_time15m | 11 | 18% | -0.027 | -0.0146 | 0.0529 | — | censored=8, time_stop=3 |
| e_time30m | 11 | 18% | -0.030 | -0.0164 | 0.0529 | — | censored=11 |
| f_first_creator_sell | 11 | 9% | -0.131 | -0.0723 | 0.0723 | — | censored=4, creator_sell=7 |
| f2_creator_sell_incl_15s_net_seller | 11 | 9% | -0.128 | -0.0703 | 0.0703 | — | censored=4, creator_sell=7 |
| g_tp30_or_trail20_or_5m | 11 | 27% | -0.101 | -0.0556 | 0.0556 | — | censored=3, target=2, time_stop=2, trailing=4 |
| g2_tp30_or_trail20_or_2m | 11 | 18% | -0.131 | -0.0719 | 0.0719 | — | target=2, time_stop=6, trailing=3 |
| g3_tp50_or_trail20_or_5m | 11 | 27% | -0.073 | -0.0400 | 0.0458 | — | censored=3, target=1, time_stop=3, trailing=4 |
| g4_tp30_or_trail15_or_5m | 11 | 18% | -0.122 | -0.0671 | 0.0671 | — | censored=2, target=2, time_stop=1, trailing=6 |
| g5_tp30_or_trail15_or_2m | 11 | 18% | -0.122 | -0.0671 | 0.0671 | — | target=2, time_stop=3, trailing=6 |
| h_tp100_or_trail30_or_5m | 11 | 36% | -0.007 | -0.0040 | 0.0458 | — | censored=4, target=1, time_stop=5, trailing=1 |
| h2_tp100_or_trail30_or_15m | 11 | 18% | -0.078 | -0.0431 | 0.0529 | — | censored=4, target=1, time_stop=3, trailing=3 |
| h3_tp100_or_trail30_or_30m | 11 | 18% | -0.081 | -0.0448 | 0.0529 | — | censored=6, target=1, trailing=4 |
| h4_tp300_or_trail30_or_30m | 11 | 18% | -0.030 | -0.0164 | 0.0529 | — | censored=7, trailing=4 |

## operator/5
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 17 | 29% | -0.023 | -0.0198 | 0.0687 | — | creator_dump=8, line_broken=8, time_stop=1 |
| a2_actual_exit_mcap_fee1.25 | 17 | 29% | -0.011 | -0.0094 | 0.0601 | — | creator_dump=8, line_broken=8, time_stop=1 |
| b_line_broken(2) | 17 | 35% | +0.100 | +0.0849 | 0.0416 | 203% | censored=7, line_broken=10 |
| b2_paper_full_set | 17 | 29% | +0.029 | +0.0246 | 0.0416 | 463% | censored=1, creator_dump=8, line_broken=8 |
| c_trail15 | 17 | 29% | -0.016 | -0.0136 | 0.0598 | — | censored=6, trailing=11 |
| c_trail30 | 17 | 29% | +0.029 | +0.0250 | 0.0679 | 599% | censored=11, trailing=6 |
| c_trail50 | 17 | 24% | -0.028 | -0.0235 | 0.1040 | — | censored=14, trailing=3 |
| d_arm+25%_trail30 | 17 | 29% | +0.029 | +0.0249 | 0.0679 | 601% | censored=13, trailing=4 |
| d_arm+50%_trail30 | 17 | 29% | +0.029 | +0.0249 | 0.0679 | 600% | censored=15, trailing=2 |
| d_arm+100%_trail30 | 17 | 29% | +0.025 | +0.0214 | 0.0715 | 699% | censored=16, trailing=1 |
| d_arm+25%_trail15 | 17 | 47% | +0.052 | +0.0441 | 0.0379 | 242% | censored=12, trailing=5 |
| d_arm+50%_trail15 | 17 | 35% | +0.033 | +0.0285 | 0.0473 | 375% | censored=14, trailing=3 |
| d_tp+25%_else_trail30 | 17 | 47% | +0.006 | +0.0050 | 0.0379 | 1021% | censored=9, target=6, trailing=2 |
| d_tp+50%_else_trail30 | 17 | 35% | +0.037 | +0.0318 | 0.0473 | 322% | censored=9, target=4, trailing=4 |
| d_tp+100%_else_trail30 | 17 | 29% | +0.043 | +0.0364 | 0.0679 | 442% | censored=9, target=3, trailing=5 |
| e_time2m | 17 | 29% | -0.036 | -0.0302 | 0.0645 | — | time_stop=17 |
| e_time5m | 17 | 41% | +0.113 | +0.0961 | 0.0715 | 191% | censored=8, time_stop=9 |
| e_time15m | 17 | 24% | -0.030 | -0.0253 | 0.1076 | — | censored=14, time_stop=3 |
| e_time30m | 17 | 24% | -0.032 | -0.0271 | 0.1076 | — | censored=17 |
| f_first_creator_sell | 17 | 18% | -0.099 | -0.0845 | 0.1462 | — | censored=8, creator_sell=9 |
| f2_creator_sell_incl_15s_net_seller | 17 | 18% | -0.097 | -0.0825 | 0.1442 | — | censored=8, creator_sell=9 |
| g_tp30_or_trail20_or_5m | 17 | 35% | -0.030 | -0.0258 | 0.0465 | — | censored=6, target=4, time_stop=2, trailing=5 |
| g2_tp30_or_trail20_or_2m | 17 | 24% | -0.078 | -0.0663 | 0.0800 | — | target=3, time_stop=9, trailing=5 |
| g3_tp50_or_trail20_or_5m | 17 | 35% | +0.017 | +0.0144 | 0.0465 | 710% | censored=6, target=3, time_stop=3, trailing=5 |
| g4_tp30_or_trail15_or_5m | 17 | 29% | -0.070 | -0.0592 | 0.0729 | — | censored=4, target=3, time_stop=1, trailing=9 |
| g5_tp30_or_trail15_or_2m | 17 | 24% | -0.079 | -0.0669 | 0.0806 | — | target=3, time_stop=7, trailing=7 |
| h_tp100_or_trail30_or_5m | 17 | 41% | +0.090 | +0.0767 | 0.0679 | 210% | censored=7, target=3, time_stop=5, trailing=2 |
| h2_tp100_or_trail30_or_15m | 17 | 29% | +0.045 | +0.0381 | 0.0679 | 422% | censored=7, target=3, time_stop=3, trailing=4 |
| h3_tp100_or_trail30_or_30m | 17 | 29% | +0.043 | +0.0364 | 0.0679 | 442% | censored=9, target=3, trailing=5 |
| h4_tp300_or_trail30_or_30m | 17 | 29% | +0.029 | +0.0250 | 0.0679 | 599% | censored=11, trailing=6 |

## flow_v2/5
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 111 | 41% | +0.011 | +0.0589 | 0.1308 | 395% | creator_dump=35, line_broken=61, max_loss=11, target=1, time_stop=2, trailing=1 |
| a2_actual_exit_mcap_fee1.25 | 111 | 45% | +0.023 | +0.1259 | 0.1253 | 188% | creator_dump=35, line_broken=61, max_loss=11, target=1, time_stop=2, trailing=1 |
| b_line_broken(2) | 111 | 44% | +0.002 | +0.0097 | 0.1317 | 2106% | censored=30, line_broken=81 |
| b2_paper_full_set | 111 | 45% | +0.013 | +0.0742 | 0.1303 | 336% | censored=2, creator_dump=38, line_broken=61, max_loss=8, target=1, trailing=1 |
| c_trail15 | 111 | 42% | +0.014 | +0.0796 | 0.2423 | 236% | censored=23, trailing=88 |
| c_trail30 | 111 | 46% | +0.007 | +0.0373 | 0.2760 | 700% | censored=54, trailing=57 |
| c_trail50 | 111 | 44% | +0.008 | +0.0463 | 0.3692 | 864% | censored=74, trailing=37 |
| d_arm+25%_trail30 | 111 | 47% | +0.005 | +0.0274 | 0.3047 | 954% | censored=83, trailing=28 |
| d_arm+50%_trail30 | 111 | 48% | +0.011 | +0.0637 | 0.3133 | 411% | censored=90, trailing=21 |
| d_arm+100%_trail30 | 111 | 46% | +0.002 | +0.0129 | 0.3277 | 2023% | censored=98, trailing=13 |
| d_arm+25%_trail15 | 111 | 52% | +0.014 | +0.0776 | 0.2741 | 242% | censored=70, trailing=41 |
| d_arm+50%_trail15 | 111 | 50% | +0.012 | +0.0645 | 0.2929 | 325% | censored=79, trailing=32 |
| d_tp+25%_else_trail30 | 111 | 60% | +0.025 | +0.1407 | 0.1635 | 63% | censored=25, target=56, trailing=30 |
| d_tp+50%_else_trail30 | 111 | 52% | +0.045 | +0.2515 | 0.2238 | 54% | censored=34, target=39, trailing=38 |
| d_tp+100%_else_trail30 | 111 | 48% | +0.073 | +0.4058 | 0.2129 | 61% | censored=44, target=20, trailing=47 |
| e_time2m | 111 | 47% | +0.014 | +0.0796 | 0.1509 | 275% | time_stop=111 |
| e_time5m | 111 | 49% | +0.019 | +0.1060 | 0.1731 | 216% | censored=75, time_stop=36 |
| e_time15m | 111 | 46% | +0.064 | +0.3550 | 0.2472 | 109% | censored=98, time_stop=13 |
| e_time30m | 111 | 44% | +0.008 | +0.0453 | 0.3581 | 882% | censored=110, time_stop=1 |
| f_first_creator_sell | 111 | 45% | +0.014 | +0.0779 | 0.3495 | 513% | censored=59, creator_sell=52 |
| f2_creator_sell_incl_15s_net_seller | 111 | 46% | +0.005 | +0.0277 | 0.3531 | 1443% | censored=59, creator_sell=52 |
| g_tp30_or_trail20_or_5m | 111 | 50% | +0.009 | +0.0478 | 0.1651 | 190% | censored=13, target=44, time_stop=6, trailing=48 |
| g2_tp30_or_trail20_or_2m | 111 | 49% | +0.003 | +0.0143 | 0.1255 | 633% | target=33, time_stop=38, trailing=40 |
| g3_tp50_or_trail20_or_5m | 111 | 47% | +0.032 | +0.1774 | 0.1462 | 77% | censored=17, target=29, time_stop=11, trailing=54 |
| g4_tp30_or_trail15_or_5m | 111 | 48% | +0.009 | +0.0476 | 0.1830 | 190% | censored=10, target=41, time_stop=5, trailing=55 |
| g5_tp30_or_trail15_or_2m | 111 | 47% | +0.004 | +0.0234 | 0.1405 | 388% | target=33, time_stop=29, trailing=49 |
| h_tp100_or_trail30_or_5m | 111 | 50% | +0.079 | +0.4372 | 0.1457 | 57% | censored=37, target=15, time_stop=19, trailing=40 |
| h2_tp100_or_trail30_or_15m | 111 | 48% | +0.089 | +0.4963 | 0.2129 | 50% | censored=39, target=20, time_stop=7, trailing=45 |
| h3_tp100_or_trail30_or_30m | 111 | 48% | +0.073 | +0.4058 | 0.2129 | 61% | censored=44, target=20, trailing=47 |
| h4_tp300_or_trail30_or_30m | 111 | 46% | +0.015 | +0.0826 | 0.2795 | 367% | censored=53, target=2, trailing=56 |

## flow_v2/2
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 127 | 42% | +0.014 | +0.0883 | 0.1712 | 321% | creator_dump=42, line_broken=68, max_loss=13, target=1, time_stop=2, trailing=1 |
| a2_actual_exit_mcap_fee1.25 | 127 | 45% | +0.026 | +0.1656 | 0.1576 | 175% | creator_dump=42, line_broken=68, max_loss=13, target=1, time_stop=2, trailing=1 |
| b_line_broken(2) | 127 | 42% | -0.010 | -0.0630 | 0.1757 | — | censored=37, line_broken=90 |
| b2_paper_full_set | 127 | 43% | +0.014 | +0.0917 | 0.1439 | 328% | censored=3, creator_dump=45, line_broken=67, max_loss=10, target=1, trailing=1 |
| c_trail15 | 127 | 41% | +0.027 | +0.1718 | 0.1887 | 109% | censored=30, trailing=97 |
| c_trail30 | 127 | 44% | +0.014 | +0.0875 | 0.2974 | 299% | censored=64, trailing=63 |
| c_trail50 | 127 | 43% | +0.007 | +0.0441 | 0.3790 | 906% | censored=87, trailing=40 |
| d_arm+25%_trail30 | 127 | 45% | +0.011 | +0.0691 | 0.3236 | 379% | censored=97, trailing=30 |
| d_arm+50%_trail30 | 127 | 46% | +0.013 | +0.0833 | 0.3253 | 314% | censored=105, trailing=22 |
| d_arm+100%_trail30 | 127 | 44% | +0.005 | +0.0326 | 0.3293 | 802% | censored=113, trailing=14 |
| d_arm+25%_trail15 | 127 | 50% | +0.020 | +0.1277 | 0.2320 | 147% | censored=83, trailing=44 |
| d_arm+50%_trail15 | 127 | 48% | +0.013 | +0.0841 | 0.2806 | 249% | censored=94, trailing=33 |
| d_tp+25%_else_trail30 | 127 | 58% | +0.045 | +0.2843 | 0.1485 | 66% | censored=30, target=63, trailing=34 |
| d_tp+50%_else_trail30 | 127 | 50% | +0.057 | +0.3590 | 0.2148 | 59% | censored=41, target=43, trailing=43 |
| d_tp+100%_else_trail30 | 127 | 46% | +0.084 | +0.5346 | 0.2307 | 57% | censored=53, target=22, trailing=52 |
| e_time2m | 127 | 47% | +0.008 | +0.0495 | 0.1832 | 442% | time_stop=127 |
| e_time5m | 127 | 46% | +0.019 | +0.1200 | 0.1934 | 190% | censored=87, time_stop=40 |
| e_time15m | 127 | 44% | +0.055 | +0.3502 | 0.3398 | 110% | censored=113, time_stop=14 |
| e_time30m | 127 | 43% | +0.006 | +0.0401 | 0.3778 | 996% | censored=126, time_stop=1 |
| f_first_creator_sell | 127 | 44% | +0.026 | +0.1655 | 0.3153 | 246% | censored=64, creator_sell=63 |
| f2_creator_sell_incl_15s_net_seller | 127 | 46% | +0.021 | +0.1320 | 0.2995 | 308% | censored=63, creator_sell=64 |
| g_tp30_or_trail20_or_5m | 127 | 48% | +0.029 | +0.1810 | 0.1510 | 103% | censored=16, target=49, time_stop=7, trailing=55 |
| g2_tp30_or_trail20_or_2m | 127 | 49% | +0.020 | +0.1262 | 0.1107 | 144% | target=35, time_stop=46, trailing=46 |
| g3_tp50_or_trail20_or_5m | 127 | 45% | +0.049 | +0.3119 | 0.1687 | 68% | censored=21, target=33, time_stop=12, trailing=61 |
| g4_tp30_or_trail15_or_5m | 127 | 46% | +0.031 | +0.1957 | 0.0992 | 96% | censored=13, target=46, time_stop=5, trailing=63 |
| g5_tp30_or_trail15_or_2m | 127 | 47% | +0.023 | +0.1485 | 0.0878 | 122% | target=35, time_stop=36, trailing=56 |
| h_tp100_or_trail30_or_5m | 127 | 48% | +0.092 | +0.5824 | 0.1800 | 52% | censored=44, target=17, time_stop=22, trailing=44 |
| h2_tp100_or_trail30_or_15m | 127 | 46% | +0.098 | +0.6250 | 0.2081 | 49% | censored=48, target=22, time_stop=7, trailing=50 |
| h3_tp100_or_trail30_or_30m | 127 | 46% | +0.084 | +0.5346 | 0.2307 | 57% | censored=53, target=22, trailing=52 |
| h4_tp300_or_trail30_or_30m | 127 | 44% | +0.032 | +0.2057 | 0.2974 | 173% | censored=63, target=3, trailing=61 |

## flow_v2/6
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 21 | 19% | +0.032 | +0.0336 | 0.0926 | 420% | creator_dump=7, line_broken=11, time_stop=3 |
| a2_actual_exit_mcap_fee1.25 | 21 | 29% | +0.045 | +0.0473 | 0.0856 | 306% | creator_dump=7, line_broken=11, time_stop=3 |
| b_line_broken(2) | 21 | 24% | +0.036 | +0.0382 | 0.0908 | 363% | censored=7, line_broken=14 |
| b2_paper_full_set | 21 | 29% | +0.043 | +0.0452 | 0.0846 | 305% | censored=3, creator_dump=7, line_broken=11 |
| c_trail15 | 21 | 24% | +0.032 | +0.0338 | 0.1069 | 469% | censored=8, trailing=13 |
| c_trail30 | 21 | 19% | -0.023 | -0.0241 | 0.1390 | — | censored=13, trailing=8 |
| c_trail50 | 21 | 14% | -0.077 | -0.0808 | 0.1667 | — | censored=18, trailing=3 |
| d_arm+25%_trail30 | 21 | 19% | -0.036 | -0.0377 | 0.1525 | — | censored=18, trailing=3 |
| d_arm+50%_trail30 | 21 | 19% | -0.036 | -0.0378 | 0.1526 | — | censored=19, trailing=2 |
| d_arm+100%_trail30 | 21 | 14% | -0.059 | -0.0619 | 0.1696 | — | censored=20, trailing=1 |
| d_arm+25%_trail15 | 21 | 24% | -0.012 | -0.0129 | 0.1455 | — | censored=17, trailing=4 |
| d_arm+50%_trail15 | 21 | 19% | -0.019 | -0.0200 | 0.1526 | — | censored=19, trailing=2 |
| d_tp+25%_else_trail30 | 21 | 29% | -0.030 | -0.0314 | 0.0896 | — | censored=10, target=6, trailing=5 |
| d_tp+50%_else_trail30 | 21 | 19% | -0.055 | -0.0577 | 0.1390 | — | censored=11, target=4, trailing=6 |
| d_tp+100%_else_trail30 | 21 | 19% | -0.021 | -0.0217 | 0.1390 | — | censored=12, target=2, trailing=7 |
| e_time2m | 21 | 19% | -0.013 | -0.0136 | 0.0998 | — | time_stop=21 |
| e_time5m | 21 | 14% | -0.095 | -0.0995 | 0.1676 | — | censored=14, time_stop=7 |
| e_time15m | 21 | 14% | -0.078 | -0.0818 | 0.1678 | — | censored=16, time_stop=5 |
| e_time30m | 21 | 14% | -0.080 | -0.0836 | 0.1696 | — | censored=21 |
| f_first_creator_sell | 21 | 19% | -0.041 | -0.0429 | 0.1591 | — | censored=14, creator_sell=7 |
| f2_creator_sell_incl_15s_net_seller | 21 | 24% | -0.070 | -0.0732 | 0.1568 | — | censored=14, creator_sell=7 |
| g_tp30_or_trail20_or_5m | 21 | 24% | -0.013 | -0.0134 | 0.0850 | — | censored=6, target=5, time_stop=1, trailing=9 |
| g2_tp30_or_trail20_or_2m | 21 | 24% | -0.019 | -0.0202 | 0.0847 | — | target=4, time_stop=9, trailing=8 |
| g3_tp50_or_trail20_or_5m | 21 | 19% | -0.030 | -0.0317 | 0.1162 | — | censored=6, target=4, time_stop=1, trailing=10 |
| g4_tp30_or_trail15_or_5m | 21 | 29% | +0.001 | +0.0007 | 0.0757 | 10189% | censored=5, target=5, time_stop=1, trailing=10 |
| g5_tp30_or_trail15_or_2m | 21 | 29% | -0.000 | -0.0001 | 0.0694 | — | target=4, time_stop=8, trailing=9 |
| h_tp100_or_trail30_or_5m | 21 | 19% | -0.032 | -0.0331 | 0.1370 | — | censored=8, target=1, time_stop=6, trailing=6 |
| h2_tp100_or_trail30_or_15m | 21 | 19% | -0.019 | -0.0200 | 0.1373 | — | censored=9, target=2, time_stop=4, trailing=6 |
| h3_tp100_or_trail30_or_30m | 21 | 19% | -0.021 | -0.0217 | 0.1390 | — | censored=12, target=2, trailing=7 |
| h4_tp300_or_trail30_or_30m | 21 | 19% | +0.028 | +0.0289 | 0.1390 | 670% | censored=13, target=1, trailing=7 |

## flow_v2/8
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 22 | 36% | +0.065 | +0.0715 | 0.0596 | 204% | creator_dump=8, line_broken=11, max_loss=1, time_stop=2 |
| a2_actual_exit_mcap_fee1.25 | 22 | 41% | +0.078 | +0.0863 | 0.0559 | 173% | creator_dump=8, line_broken=11, max_loss=1, time_stop=2 |
| b_line_broken(2) | 22 | 32% | +0.061 | +0.0676 | 0.0571 | 208% | censored=6, line_broken=16 |
| b2_paper_full_set | 22 | 45% | +0.081 | +0.0895 | 0.0436 | 156% | censored=2, creator_dump=8, line_broken=11, max_loss=1 |
| c_trail15 | 22 | 32% | +0.043 | +0.0475 | 0.0934 | 364% | censored=9, trailing=13 |
| c_trail30 | 22 | 23% | -0.002 | -0.0020 | 0.1131 | — | censored=15, trailing=7 |
| c_trail50 | 22 | 23% | -0.048 | -0.0533 | 0.1491 | — | censored=19, trailing=3 |
| d_arm+25%_trail30 | 22 | 23% | -0.038 | -0.0416 | 0.1456 | — | censored=20, trailing=2 |
| d_arm+50%_trail30 | 22 | 23% | -0.038 | -0.0417 | 0.1457 | — | censored=21, trailing=1 |
| d_arm+100%_trail30 | 22 | 23% | -0.038 | -0.0417 | 0.1457 | — | censored=21, trailing=1 |
| d_arm+25%_trail15 | 22 | 27% | -0.015 | -0.0168 | 0.1386 | — | censored=18, trailing=4 |
| d_arm+50%_trail15 | 22 | 23% | -0.022 | -0.0239 | 0.1457 | — | censored=21, trailing=1 |
| d_tp+25%_else_trail30 | 22 | 32% | -0.006 | -0.0067 | 0.0790 | — | censored=10, target=7, trailing=5 |
| d_tp+50%_else_trail30 | 22 | 23% | -0.047 | -0.0520 | 0.1228 | — | censored=12, target=4, trailing=6 |
| d_tp+100%_else_trail30 | 22 | 23% | +0.000 | +0.0004 | 0.1131 | 35292% | censored=14, target=2, trailing=6 |
| e_time2m | 22 | 32% | -0.008 | -0.0086 | 0.0698 | — | time_stop=22 |
| e_time5m | 22 | 23% | -0.074 | -0.0810 | 0.1519 | — | censored=17, time_stop=5 |
| e_time15m | 22 | 23% | -0.058 | -0.0634 | 0.1592 | — | censored=18, time_stop=4 |
| e_time30m | 22 | 23% | -0.058 | -0.0635 | 0.1593 | — | censored=22 |
| f_first_creator_sell | 22 | 36% | -0.009 | -0.0094 | 0.1295 | — | censored=14, creator_sell=8 |
| f2_creator_sell_incl_15s_net_seller | 22 | 36% | -0.044 | -0.0479 | 0.1437 | — | censored=14, creator_sell=8 |
| g_tp30_or_trail20_or_5m | 22 | 27% | +0.001 | +0.0010 | 0.0700 | 9131% | censored=6, target=6, time_stop=1, trailing=9 |
| g2_tp30_or_trail20_or_2m | 22 | 32% | +0.004 | +0.0040 | 0.0670 | 2239% | target=5, time_stop=8, trailing=9 |
| g3_tp50_or_trail20_or_5m | 22 | 23% | -0.030 | -0.0328 | 0.1035 | — | censored=6, target=4, time_stop=1, trailing=11 |
| g4_tp30_or_trail15_or_5m | 22 | 36% | +0.012 | +0.0134 | 0.0575 | 664% | censored=5, target=6, time_stop=1, trailing=10 |
| g5_tp30_or_trail15_or_2m | 22 | 36% | +0.013 | +0.0148 | 0.0562 | 602% | target=5, time_stop=8, trailing=9 |
| h_tp100_or_trail30_or_5m | 22 | 23% | -0.011 | -0.0125 | 0.1127 | — | censored=11, target=1, time_stop=4, trailing=6 |
| h2_tp100_or_trail30_or_15m | 22 | 23% | +0.000 | +0.0004 | 0.1131 | 35292% | censored=11, target=2, time_stop=3, trailing=6 |
| h3_tp100_or_trail30_or_30m | 22 | 23% | +0.000 | +0.0004 | 0.1131 | 35292% | censored=14, target=2, trailing=6 |
| h4_tp300_or_trail30_or_30m | 22 | 23% | +0.046 | +0.0510 | 0.1131 | 408% | censored=15, target=1, trailing=6 |

## papel (5 sets)
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 298 | 39% | +0.016 | +0.2325 | 0.3153 | 133% | creator_dump=100, line_broken=159, max_loss=25, target=2, time_stop=10, trailing=2 |
| a2_actual_exit_mcap_fee1.25 | 298 | 43% | +0.028 | +0.4157 | 0.3030 | 76% | creator_dump=100, line_broken=159, max_loss=25, target=2, time_stop=10, trailing=2 |
| b_line_broken(2) | 298 | 40% | +0.009 | +0.1373 | 0.3112 | 158% | censored=87, line_broken=211 |
| b2_paper_full_set | 298 | 42% | +0.022 | +0.3251 | 0.2272 | 104% | censored=11, creator_dump=106, line_broken=158, max_loss=19, target=2, trailing=2 |
| c_trail15 | 298 | 39% | +0.021 | +0.3191 | 0.4339 | 72% | censored=76, trailing=222 |
| c_trail30 | 298 | 41% | +0.008 | +0.1238 | 0.4737 | 266% | censored=157, trailing=141 |
| c_trail50 | 298 | 39% | -0.005 | -0.0671 | 0.8124 | — | censored=212, trailing=86 |
| d_arm+25%_trail30 | 298 | 41% | +0.003 | +0.0420 | 0.5794 | 784% | censored=231, trailing=67 |
| d_arm+50%_trail30 | 298 | 42% | +0.006 | +0.0924 | 0.5969 | 357% | censored=250, trailing=48 |
| d_arm+100%_trail30 | 298 | 40% | -0.002 | -0.0367 | 0.6292 | — | censored=268, trailing=30 |
| d_arm+25%_trail15 | 298 | 47% | +0.015 | +0.2197 | 0.5305 | 104% | censored=200, trailing=98 |
| d_arm+50%_trail15 | 298 | 44% | +0.009 | +0.1332 | 0.5877 | 178% | censored=227, trailing=71 |
| d_tp+25%_else_trail30 | 298 | 54% | +0.026 | +0.3919 | 0.2218 | 49% | censored=84, target=138, trailing=76 |
| d_tp+50%_else_trail30 | 298 | 46% | +0.036 | +0.5325 | 0.3977 | 40% | censored=107, target=94, trailing=97 |
| d_tp+100%_else_trail30 | 298 | 42% | +0.064 | +0.9556 | 0.3652 | 33% | censored=132, target=49, trailing=117 |
| e_time2m | 298 | 43% | +0.005 | +0.0767 | 0.3599 | 349% | time_stop=298 |
| e_time5m | 298 | 43% | +0.009 | +0.1415 | 0.3827 | 183% | censored=201, time_stop=97 |
| e_time15m | 298 | 40% | +0.036 | +0.5347 | 0.5635 | 80% | censored=259, time_stop=39 |
| e_time30m | 298 | 39% | -0.006 | -0.0887 | 0.8068 | — | censored=296, time_stop=2 |
| f_first_creator_sell | 298 | 41% | +0.007 | +0.1066 | 0.6776 | 417% | censored=159, creator_sell=139 |
| f2_creator_sell_incl_15s_net_seller | 298 | 42% | -0.003 | -0.0438 | 0.7360 | — | censored=158, creator_sell=140 |
| g_tp30_or_trail20_or_5m | 298 | 45% | +0.013 | +0.1906 | 0.2419 | 101% | censored=47, target=108, time_stop=17, trailing=126 |
| g2_tp30_or_trail20_or_2m | 298 | 44% | +0.004 | +0.0579 | 0.2323 | 330% | target=80, time_stop=110, trailing=108 |
| g3_tp50_or_trail20_or_5m | 298 | 42% | +0.029 | +0.4392 | 0.2744 | 48% | censored=56, target=73, time_stop=28, trailing=141 |
| g4_tp30_or_trail15_or_5m | 298 | 44% | +0.013 | +0.1982 | 0.2243 | 97% | censored=37, target=101, time_stop=13, trailing=147 |
| g5_tp30_or_trail15_or_2m | 298 | 44% | +0.008 | +0.1196 | 0.1773 | 160% | target=80, time_stop=88, trailing=130 |
| h_tp100_or_trail30_or_5m | 298 | 45% | +0.071 | +1.0506 | 0.3154 | 30% | censored=107, target=37, time_stop=56, trailing=98 |
| h2_tp100_or_trail30_or_15m | 298 | 42% | +0.077 | +1.1399 | 0.3652 | 27% | censored=114, target=49, time_stop=24, trailing=111 |
| h3_tp100_or_trail30_or_30m | 298 | 42% | +0.064 | +0.9556 | 0.3652 | 33% | censored=132, target=49, trailing=117 |
| h4_tp300_or_trail30_or_30m | 298 | 41% | +0.026 | +0.3932 | 0.4151 | 95% | censored=155, target=7, trailing=136 |

## papel unico (mint@minuto)
| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |
|---|---|---|---|---|---|---|---|
| a_actual_recorded | 168 | 38% | +0.008 | +0.0659 | 0.1720 | 430% | creator_dump=59, line_broken=88, max_loss=14, target=1, time_stop=5, trailing=1 |
| a2_actual_exit_mcap_fee1.25 | 168 | 42% | +0.020 | +0.1688 | 0.1576 | 171% | creator_dump=59, line_broken=88, max_loss=14, target=1, time_stop=5, trailing=1 |
| b_line_broken(2) | 168 | 39% | -0.001 | -0.0111 | 0.1956 | — | censored=51, line_broken=117 |
| b2_paper_full_set | 168 | 41% | +0.013 | +0.1066 | 0.1564 | 283% | censored=6, creator_dump=62, line_broken=87, max_loss=11, target=1, trailing=1 |
| c_trail15 | 168 | 38% | +0.024 | +0.2009 | 0.2279 | 108% | censored=46, trailing=122 |
| c_trail30 | 168 | 39% | +0.006 | +0.0546 | 0.2237 | 491% | censored=91, trailing=77 |
| c_trail50 | 168 | 37% | -0.009 | -0.0749 | 0.3583 | — | censored=123, trailing=45 |
| d_arm+25%_trail30 | 168 | 39% | -0.002 | -0.0170 | 0.2698 | — | censored=133, trailing=35 |
| d_arm+50%_trail30 | 168 | 40% | -0.000 | -0.0028 | 0.2769 | — | censored=144, trailing=24 |
| d_arm+100%_trail30 | 168 | 38% | -0.009 | -0.0776 | 0.2831 | — | censored=153, trailing=15 |
| d_arm+25%_trail15 | 168 | 45% | +0.010 | +0.0820 | 0.2920 | 264% | censored=117, trailing=51 |
| d_arm+50%_trail15 | 168 | 42% | +0.002 | +0.0158 | 0.3206 | 1439% | censored=133, trailing=35 |
| d_tp+25%_else_trail30 | 168 | 52% | +0.028 | +0.2336 | 0.1132 | 83% | censored=51, target=74, trailing=43 |
| d_tp+50%_else_trail30 | 168 | 43% | +0.030 | +0.2551 | 0.2152 | 83% | censored=64, target=49, trailing=55 |
| d_tp+100%_else_trail30 | 168 | 40% | +0.058 | +0.4891 | 0.2152 | 62% | censored=78, target=25, trailing=65 |
| e_time2m | 168 | 41% | -0.006 | -0.0518 | 0.2197 | — | time_stop=168 |
| e_time5m | 168 | 41% | +0.000 | +0.0011 | 0.2306 | 21167% | censored=118, time_stop=50 |
| e_time15m | 168 | 38% | +0.026 | +0.2201 | 0.3017 | 175% | censored=149, time_stop=19 |
| e_time30m | 168 | 37% | -0.011 | -0.0918 | 0.3601 | — | censored=167, time_stop=1 |
| f_first_creator_sell | 168 | 39% | +0.004 | +0.0315 | 0.3154 | 1292% | censored=88, creator_sell=80 |
| f2_creator_sell_incl_15s_net_seller | 168 | 40% | -0.004 | -0.0365 | 0.3363 | — | censored=87, creator_sell=81 |
| g_tp30_or_trail20_or_5m | 168 | 43% | +0.017 | +0.1396 | 0.1334 | 138% | censored=31, target=58, time_stop=8, trailing=71 |
| g2_tp30_or_trail20_or_2m | 168 | 43% | +0.008 | +0.0666 | 0.1352 | 287% | target=43, time_stop=64, trailing=61 |
| g3_tp50_or_trail20_or_5m | 168 | 40% | +0.030 | +0.2481 | 0.1494 | 85% | censored=36, target=39, time_stop=14, trailing=79 |
| g4_tp30_or_trail15_or_5m | 168 | 42% | +0.019 | +0.1618 | 0.1046 | 119% | censored=24, target=55, time_stop=6, trailing=83 |
| g5_tp30_or_trail15_or_2m | 168 | 42% | +0.013 | +0.1120 | 0.1090 | 171% | target=43, time_stop=52, trailing=73 |
| h_tp100_or_trail30_or_5m | 168 | 43% | +0.066 | +0.5566 | 0.1568 | 55% | censored=65, target=19, time_stop=30, trailing=54 |
| h2_tp100_or_trail30_or_15m | 168 | 40% | +0.069 | +0.5812 | 0.2152 | 52% | censored=70, target=25, time_stop=11, trailing=62 |
| h3_tp100_or_trail30_or_30m | 168 | 40% | +0.058 | +0.4891 | 0.2152 | 62% | censored=78, target=25, trailing=65 |
| h4_tp300_or_trail30_or_30m | 168 | 39% | +0.027 | +0.2257 | 0.2152 | 160% | censored=90, target=4, trailing=74 |

## as posicoes reais, aposta a aposta (PnL a 0,05 SOL, taxas 1,25 %)
| mint | cobertura | a_actual_recorded | b_line_broken(2) | c_trail15 | c_trail30 | e_time2m | e_time5m | f_first_creator_sell | g_tp30_or_trail20_or_5m | g5_tp30_or_trail15_or_2m |
|---|---|---|---|---|---|---|---|---|---|---|
| 7s4dKmpv | 214s | -0.0093 (creator_dump, 48s) | -0.0116 (censored, 214s) | -0.0108 (trailing, 119s) | -0.0116 (censored, 214s) | -0.0108 (time_stop, 135s) | -0.0116 (censored, 214s) | -0.0067 (creator_sell, 55s) | -0.0116 (trailing, 214s) | -0.0108 (trailing, 119s) |
| 63NPcW9q | 94s | -0.0035 (creator_dump, 52s) | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie | sem serie |
| CCLstvwa | 394s | -0.0071 (trailing, 396s) | -0.0117 (line_broken, 56s) | -0.0101 (trailing, 24s) | -0.0058 (trailing, 394s) | -0.0115 (time_stop, 121s) | +0.0143 (time_stop, 314s) | -0.0058 (censored, 394s) | -0.0117 (trailing, 40s) | -0.0101 (trailing, 24s) |
| 2hhJXPy3 | 1557s | -0.0176 (time_stop, 1800s) | -0.0166 (censored, 1557s) | -0.0104 (trailing, 20s) | -0.0165 (trailing, 1366s) | -0.0148 (time_stop, 132s) | -0.0148 (time_stop, 307s) | -0.0166 (censored, 1557s) | -0.0131 (trailing, 52s) | -0.0104 (trailing, 20s) |
| Dy9YAbcL | 514s | -0.0059 (creator_dump, 514s) | +0.0122 (line_broken, 204s) | +0.0030 (trailing, 338s) | -0.0046 (trailing, 449s) | +0.0146 (time_stop, 124s) | +0.0072 (time_stop, 306s) | -0.0048 (creator_sell, 465s) | +0.0139 (target, 93s) | +0.0139 (target, 93s) |
| GdZ5hSdz | 179s | -0.0038 (creator_dump, 86s) | -0.0030 (censored, 179s) | -0.0030 (censored, 179s) | -0.0030 (censored, 179s) | -0.0030 (time_stop, 129s) | -0.0030 (censored, 179s) | -0.0030 (creator_sell, 96s) | -0.0030 (censored, 179s) | -0.0030 (time_stop, 129s) |
| 6zdT1MxC | 417s | +0.0329 (creator_dump, 117s) | +0.0811 (line_broken, 383s) | +0.0780 (censored, 417s) | +0.0780 (censored, 417s) | +0.0352 (time_stop, 121s) | +0.0621 (time_stop, 302s) | +0.0186 (creator_sell, 55s) | +0.0157 (target, 39s) | +0.0157 (target, 39s) |
| rYJYP8jV | 157s | -0.0040 (creator_dump, 45s) | -0.0040 (line_broken, 124s) | -0.0040 (censored, 157s) | -0.0040 (censored, 157s) | -0.0040 (time_stop, 124s) | -0.0040 (censored, 157s) | -0.0026 (creator_sell, 42s) | -0.0040 (censored, 157s) | -0.0040 (time_stop, 124s) |
| M3kpWCVA | 1586s | -0.0122 (time_stop, 1804s) | -0.0074 (line_broken, 31s) | -0.0089 (trailing, 63s) | -0.0110 (censored, 1586s) | -0.0105 (time_stop, 129s) | -0.0040 (time_stop, 308s) | -0.0110 (censored, 1586s) | -0.0040 (time_stop, 308s) | -0.0089 (trailing, 63s) |
| 8DqtPVgJ | 207s | -0.0025 (creator_dump, 33s) | +0.0015 (censored, 207s) | -0.0103 (trailing, 60s) | +0.0015 (censored, 207s) | -0.0090 (time_stop, 125s) | +0.0015 (censored, 207s) | -0.0011 (creator_sell, 44s) | +0.0015 (censored, 207s) | -0.0103 (trailing, 60s) |
| 4c3rRxkp | 1738s | -0.0029 (time_stop, 1804s) | -0.0014 (line_broken, 124s) | -0.0014 (censored, 1738s) | -0.0014 (censored, 1738s) | -0.0014 (time_stop, 124s) | -0.0014 (time_stop, 315s) | -0.0014 (censored, 1738s) | -0.0014 (time_stop, 315s) | -0.0014 (time_stop, 124s) |
| ADxEynfQ | 212s | -0.0383 (trailing, 43s) | -0.0379 (censored, 212s) | -0.0379 (trailing, 52s) | -0.0379 (trailing, 52s) | -0.0379 (time_stop, 132s) | -0.0379 (censored, 212s) | -0.0379 (creator_sell, 132s) | -0.0379 (trailing, 52s) | -0.0379 (trailing, 52s) |

## top-3 contribuintes (papel unico)
- a2_actual_exit_mcap_fee1.25: soma +0.1688; top3 = 4XYuRzrB +0.1201 (creator_dump, 0s); fsnuqm67 +0.0972 (target, 0s); H88Srjvu +0.0719 (line_broken, 0s)
- c_trail15: soma +0.2009; top3 = 5hmWwRNw +0.0793 (trailing, 101s); 6zdT1MxC +0.0702 (censored, 412s); 81ZGuscZ +0.0670 (trailing, 362s)
- c_trail30: soma +0.0546; top3 = H88Srjvu +0.1297 (censored, 1323s); 6zdT1MxC +0.0702 (censored, 412s); EuS3oJQ9 +0.0682 (censored, 618s)
- d_tp+100%_else_trail30: soma +0.4891; top3 = 4XYuRzrB +0.1201 (target, 54s); fsnuqm67 +0.0954 (target, 132s); 81ZGuscZ +0.0892 (target, 284s)
- e_time5m: soma +0.0011; top3 = fsnuqm67 +0.0930 (time_stop, 343s); 81ZGuscZ +0.0734 (time_stop, 315s); 6zdT1MxC +0.0682 (time_stop, 313s)

## ranking (soma SOL, top3 < 50 %)
- papel (5 sets): melhor com top3<50%: h2_tp100_or_trail30_or_15m (+1.1399, top3 27%), h_tp100_or_trail30_or_5m (+1.0506, top3 30%), d_tp+100%_else_trail30 (+0.9556, top3 33%), h3_tp100_or_trail30_or_30m (+0.9556, top3 33%) | melhor absoluta: h2_tp100_or_trail30_or_15m (+1.1399, top3 27%)
- papel unico (mint@minuto): melhor com top3<50%: nenhuma | melhor absoluta: h2_tp100_or_trail30_or_15m (+0.5812, top3 52%)
- operator/5 real: melhor com top3<50%: nenhuma | melhor absoluta: e_time5m (+0.0084, top3 991%)
- operator/5: melhor com top3<50%: nenhuma | melhor absoluta: e_time5m (+0.0961, top3 191%)
- flow_v2/5: melhor com top3<50%: nenhuma | melhor absoluta: h2_tp100_or_trail30_or_15m (+0.4963, top3 50%)
- flow_v2/2: melhor com top3<50%: h2_tp100_or_trail30_or_15m (+0.6250, top3 49%) | melhor absoluta: h2_tp100_or_trail30_or_15m (+0.6250, top3 49%)
- flow_v2/6: melhor com top3<50%: nenhuma | melhor absoluta: a2_actual_exit_mcap_fee1.25 (+0.0473, top3 306%)
- flow_v2/8: melhor com top3<50%: nenhuma | melhor absoluta: b2_paper_full_set (+0.0895, top3 156%)

## delta pareado por aposta (regra - saida registrada a 1,25 %), modo=hold

### papel unico (mint@minuto) (n=168)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 42 | 61 | 65 | +0.0000 | -0.1799 | 39% | 0.08 |
| b2_paper_full_set | 49 | 30 | 89 | +0.0000 | -0.0622 | 35% | 0.04 |
| c_trail15 | 72 | 79 | 17 | +0.0000 | +0.0321 | 14% | 0.63 |
| c_trail30 | 79 | 65 | 24 | +0.0000 | -0.1142 | 18% | 0.28 |
| c_trail50 | 69 | 74 | 25 | +0.0000 | -0.2437 | 21% | 0.74 |
| d_arm+25%_trail30 | 65 | 83 | 20 | +0.0000 | -0.1858 | 18% | 0.16 |
| d_arm+50%_trail30 | 64 | 86 | 18 | -0.0000 | -0.1716 | 18% | 0.09 |
| d_arm+100%_trail30 | 62 | 88 | 18 | -0.0000 | -0.2464 | 19% | 0.04 |
| d_arm+25%_trail15 | 64 | 85 | 19 | -0.0000 | -0.0867 | 19% | 0.10 |
| d_arm+50%_trail15 | 63 | 88 | 17 | -0.0000 | -0.1530 | 19% | 0.05 |
| d_tp+25%_else_trail30 | 80 | 65 | 23 | +0.0000 | +0.0648 | 17% | 0.24 |
| d_tp+50%_else_trail30 | 78 | 65 | 25 | +0.0000 | +0.0863 | 16% | 0.32 |
| d_tp+100%_else_trail30 | 82 | 62 | 24 | +0.0000 | +0.3203 | 16% | 0.11 |
| e_time2m | 70 | 78 | 20 | +0.0000 | -0.2206 | 18% | 0.57 |
| e_time5m | 68 | 89 | 11 | -0.0000 | -0.1677 | 16% | 0.11 |
| e_time15m | 67 | 86 | 15 | -0.0000 | +0.0513 | 23% | 0.15 |
| e_time30m | 62 | 90 | 16 | -0.0001 | -0.2606 | 20% | 0.03 |
| f_first_creator_sell | 61 | 63 | 44 | +0.0000 | -0.1373 | 27% | 0.93 |
| f2_creator_sell_incl_15s_net_seller | 71 | 65 | 32 | +0.0000 | -0.2053 | 26% | 0.67 |
| g_tp30_or_trail20_or_5m | 70 | 75 | 23 | +0.0000 | -0.0292 | 17% | 0.74 |
| g2_tp30_or_trail20_or_2m | 76 | 68 | 24 | +0.0000 | -0.1022 | 21% | 0.56 |
| g3_tp50_or_trail20_or_5m | 70 | 74 | 24 | +0.0000 | +0.0793 | 17% | 0.80 |
| g4_tp30_or_trail15_or_5m | 68 | 80 | 20 | +0.0000 | -0.0070 | 17% | 0.37 |
| g5_tp30_or_trail15_or_2m | 77 | 71 | 20 | +0.0000 | -0.0568 | 19% | 0.68 |
| h_tp100_or_trail30_or_5m | 85 | 62 | 21 | +0.0000 | +0.3878 | 16% | 0.07 |
| h2_tp100_or_trail30_or_15m | 83 | 61 | 24 | +0.0000 | +0.4124 | 16% | 0.08 |
| h3_tp100_or_trail30_or_30m | 82 | 62 | 24 | +0.0000 | +0.3203 | 16% | 0.11 |
| h4_tp300_or_trail30_or_30m | 81 | 62 | 25 | +0.0000 | +0.0569 | 16% | 0.13 |

### operator/5 real (n=11)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 6 | 5 | 0 | +0.0001 | +0.0575 | 96% | 1.00 |
| b2_paper_full_set | 7 | 3 | 1 | +0.0001 | -0.0012 | 97% | 0.34 |
| c_trail15 | 5 | 5 | 1 | -0.0000 | +0.0406 | 96% | 1.00 |
| c_trail30 | 7 | 3 | 1 | +0.0001 | +0.0399 | 99% | 0.34 |
| c_trail50 | 7 | 3 | 1 | +0.0001 | +0.0399 | 99% | 0.34 |
| d_arm+25%_trail30 | 7 | 4 | 0 | +0.0001 | +0.0398 | 99% | 0.55 |
| d_arm+50%_trail30 | 7 | 4 | 0 | +0.0001 | +0.0399 | 99% | 0.55 |
| d_arm+100%_trail30 | 7 | 4 | 0 | +0.0001 | +0.0399 | 99% | 0.55 |
| d_arm+25%_trail15 | 7 | 4 | 0 | +0.0001 | +0.0555 | 95% | 0.55 |
| d_arm+50%_trail15 | 7 | 4 | 0 | +0.0001 | +0.0399 | 99% | 0.55 |
| d_tp+25%_else_trail30 | 6 | 4 | 1 | +0.0001 | +0.0174 | 99% | 0.75 |
| d_tp+50%_else_trail30 | 7 | 3 | 1 | +0.0001 | -0.0001 | 93% | 0.34 |
| d_tp+100%_else_trail30 | 7 | 3 | 1 | +0.0001 | +0.0115 | 98% | 0.34 |
| e_time2m | 4 | 6 | 1 | -0.0000 | +0.0031 | 99% | 0.75 |
| e_time5m | 7 | 4 | 0 | +0.0019 | +0.0647 | 83% | 0.55 |
| e_time15m | 7 | 4 | 0 | +0.0001 | +0.0416 | 99% | 0.55 |
| e_time30m | 7 | 4 | 0 | +0.0001 | +0.0399 | 99% | 0.55 |
| f_first_creator_sell | 7 | 4 | 0 | +0.0001 | -0.0160 | 58% | 0.55 |
| f2_creator_sell_incl_15s_net_seller | 8 | 3 | 0 | +0.0001 | -0.0140 | 77% | 0.23 |
| g_tp30_or_trail20_or_5m | 5 | 5 | 1 | -0.0000 | +0.0006 | 91% | 1.00 |
| g2_tp30_or_trail20_or_2m | 4 | 6 | 1 | -0.0005 | -0.0157 | 99% | 0.75 |
| g3_tp50_or_trail20_or_5m | 6 | 4 | 1 | +0.0002 | +0.0163 | 80% | 0.75 |
| g4_tp30_or_trail15_or_5m | 4 | 6 | 1 | -0.0005 | -0.0109 | 99% | 0.75 |
| g5_tp30_or_trail15_or_2m | 4 | 6 | 1 | -0.0005 | -0.0108 | 99% | 0.75 |
| h_tp100_or_trail30_or_5m | 7 | 3 | 1 | +0.0019 | +0.0522 | 80% | 0.34 |
| h2_tp100_or_trail30_or_15m | 7 | 3 | 1 | +0.0001 | +0.0132 | 98% | 0.34 |
| h3_tp100_or_trail30_or_30m | 7 | 3 | 1 | +0.0001 | +0.0115 | 98% | 0.34 |
| h4_tp300_or_trail30_or_30m | 7 | 3 | 1 | +0.0001 | +0.0399 | 99% | 0.34 |

### operator/5 (n=17)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 6 | 6 | 5 | +0.0000 | +0.0942 | 97% | 1.00 |
| b2_paper_full_set | 6 | 3 | 8 | +0.0000 | +0.0340 | 99% | 0.51 |
| c_trail15 | 5 | 9 | 3 | -0.0000 | -0.0042 | 94% | 0.42 |
| c_trail30 | 7 | 6 | 4 | +0.0000 | +0.0344 | 85% | 1.00 |
| c_trail50 | 7 | 7 | 3 | +0.0000 | -0.0141 | 85% | 1.00 |
| d_arm+25%_trail30 | 7 | 7 | 3 | +0.0000 | +0.0343 | 85% | 1.00 |
| d_arm+50%_trail30 | 7 | 7 | 3 | +0.0000 | +0.0343 | 85% | 1.00 |
| d_arm+100%_trail30 | 7 | 7 | 3 | +0.0000 | +0.0308 | 85% | 1.00 |
| d_arm+25%_trail15 | 7 | 7 | 3 | +0.0000 | +0.0535 | 85% | 1.00 |
| d_arm+50%_trail15 | 7 | 7 | 3 | +0.0000 | +0.0379 | 87% | 1.00 |
| d_tp+25%_else_trail30 | 8 | 6 | 3 | +0.0000 | +0.0144 | 86% | 0.79 |
| d_tp+50%_else_trail30 | 8 | 6 | 3 | +0.0000 | +0.0412 | 74% | 0.79 |
| d_tp+100%_else_trail30 | 7 | 6 | 4 | +0.0000 | +0.0458 | 87% | 1.00 |
| e_time2m | 6 | 7 | 4 | +0.0000 | -0.0208 | 94% | 1.00 |
| e_time5m | 8 | 6 | 3 | +0.0000 | +0.1055 | 85% | 0.79 |
| e_time15m | 7 | 8 | 2 | +0.0000 | -0.0159 | 84% | 1.00 |
| e_time30m | 7 | 8 | 2 | +0.0000 | -0.0177 | 85% | 1.00 |
| f_first_creator_sell | 7 | 5 | 5 | +0.0000 | -0.0751 | 68% | 0.77 |
| f2_creator_sell_incl_15s_net_seller | 9 | 5 | 3 | +0.0001 | -0.0731 | 63% | 0.42 |
| g_tp30_or_trail20_or_5m | 7 | 6 | 4 | +0.0000 | -0.0164 | 61% | 1.00 |
| g2_tp30_or_trail20_or_2m | 4 | 8 | 5 | +0.0000 | -0.0569 | 94% | 0.39 |
| g3_tp50_or_trail20_or_5m | 6 | 7 | 4 | +0.0000 | +0.0238 | 82% | 1.00 |
| g4_tp30_or_trail15_or_5m | 6 | 8 | 3 | +0.0000 | -0.0498 | 75% | 0.79 |
| g5_tp30_or_trail15_or_2m | 6 | 7 | 4 | +0.0000 | -0.0575 | 78% | 1.00 |
| h_tp100_or_trail30_or_5m | 8 | 5 | 4 | +0.0000 | +0.0861 | 82% | 0.58 |
| h2_tp100_or_trail30_or_15m | 7 | 6 | 4 | +0.0000 | +0.0475 | 86% | 1.00 |
| h3_tp100_or_trail30_or_30m | 7 | 6 | 4 | +0.0000 | +0.0458 | 87% | 1.00 |
| h4_tp300_or_trail30_or_30m | 7 | 6 | 4 | +0.0000 | +0.0344 | 85% | 1.00 |

### flow_v2/5 (n=111)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 24 | 39 | 48 | +0.0000 | -0.1162 | 41% | 0.08 |
| b2_paper_full_set | 27 | 22 | 62 | +0.0000 | -0.0517 | 46% | 0.57 |
| c_trail15 | 47 | 53 | 11 | +0.0000 | -0.0463 | 15% | 0.62 |
| c_trail30 | 55 | 39 | 17 | +0.0000 | -0.0886 | 19% | 0.12 |
| c_trail50 | 51 | 43 | 17 | +0.0000 | -0.0796 | 26% | 0.47 |
| d_arm+25%_trail30 | 48 | 50 | 13 | +0.0000 | -0.0985 | 21% | 0.92 |
| d_arm+50%_trail30 | 48 | 52 | 11 | +0.0000 | -0.0622 | 21% | 0.76 |
| d_arm+100%_trail30 | 47 | 53 | 11 | +0.0000 | -0.1130 | 21% | 0.62 |
| d_arm+25%_trail15 | 46 | 54 | 11 | +0.0000 | -0.0483 | 21% | 0.48 |
| d_arm+50%_trail15 | 46 | 55 | 10 | +0.0000 | -0.0614 | 24% | 0.43 |
| d_tp+25%_else_trail30 | 54 | 42 | 15 | +0.0000 | +0.0148 | 22% | 0.26 |
| d_tp+50%_else_trail30 | 55 | 39 | 17 | +0.0000 | +0.1256 | 21% | 0.12 |
| d_tp+100%_else_trail30 | 58 | 38 | 15 | +0.0001 | +0.2799 | 21% | 0.05 |
| e_time2m | 48 | 52 | 11 | +0.0000 | -0.0463 | 21% | 0.76 |
| e_time5m | 50 | 54 | 7 | +0.0000 | -0.0199 | 16% | 0.77 |
| e_time15m | 51 | 51 | 9 | +0.0000 | +0.2291 | 28% | 1.00 |
| e_time30m | 47 | 55 | 9 | +0.0000 | -0.0806 | 25% | 0.49 |
| f_first_creator_sell | 42 | 42 | 27 | +0.0000 | -0.0480 | 33% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 45 | 43 | 23 | +0.0000 | -0.0982 | 33% | 0.92 |
| g_tp30_or_trail20_or_5m | 46 | 50 | 15 | +0.0000 | -0.0781 | 24% | 0.76 |
| g2_tp30_or_trail20_or_2m | 49 | 47 | 15 | +0.0000 | -0.1116 | 27% | 0.92 |
| g3_tp50_or_trail20_or_5m | 48 | 47 | 16 | +0.0000 | +0.0515 | 24% | 1.00 |
| g4_tp30_or_trail15_or_5m | 43 | 55 | 13 | +0.0000 | -0.0783 | 24% | 0.27 |
| g5_tp30_or_trail15_or_2m | 47 | 52 | 12 | +0.0000 | -0.1025 | 26% | 0.69 |
| h_tp100_or_trail30_or_5m | 60 | 38 | 13 | +0.0009 | +0.3113 | 20% | 0.03 |
| h2_tp100_or_trail30_or_15m | 59 | 37 | 15 | +0.0001 | +0.3703 | 20% | 0.03 |
| h3_tp100_or_trail30_or_30m | 58 | 38 | 15 | +0.0001 | +0.2799 | 21% | 0.05 |
| h4_tp300_or_trail30_or_30m | 56 | 38 | 17 | +0.0000 | -0.0433 | 18% | 0.08 |

### flow_v2/2 (n=127)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 30 | 46 | 51 | +0.0000 | -0.2286 | 37% | 0.08 |
| b2_paper_full_set | 35 | 25 | 67 | +0.0000 | -0.0739 | 42% | 0.25 |
| c_trail15 | 57 | 59 | 11 | +0.0000 | +0.0062 | 14% | 0.93 |
| c_trail30 | 65 | 44 | 18 | +0.0000 | -0.0781 | 18% | 0.05 |
| c_trail50 | 58 | 50 | 19 | +0.0000 | -0.1215 | 23% | 0.50 |
| d_arm+25%_trail30 | 55 | 58 | 14 | +0.0000 | -0.0965 | 19% | 0.85 |
| d_arm+50%_trail30 | 54 | 61 | 12 | +0.0000 | -0.0823 | 19% | 0.58 |
| d_arm+100%_trail30 | 53 | 62 | 12 | +0.0000 | -0.1330 | 19% | 0.46 |
| d_arm+25%_trail15 | 53 | 62 | 12 | +0.0000 | -0.0379 | 19% | 0.46 |
| d_arm+50%_trail15 | 52 | 64 | 11 | -0.0000 | -0.0815 | 21% | 0.31 |
| d_tp+25%_else_trail30 | 65 | 45 | 17 | +0.0000 | +0.1187 | 19% | 0.07 |
| d_tp+50%_else_trail30 | 65 | 43 | 19 | +0.0000 | +0.1934 | 18% | 0.04 |
| d_tp+100%_else_trail30 | 68 | 42 | 17 | +0.0003 | +0.3690 | 18% | 0.02 |
| e_time2m | 57 | 58 | 12 | +0.0000 | -0.1161 | 19% | 1.00 |
| e_time5m | 57 | 63 | 7 | +0.0000 | -0.0456 | 16% | 0.65 |
| e_time15m | 57 | 60 | 10 | +0.0000 | +0.1846 | 25% | 0.85 |
| e_time30m | 53 | 64 | 10 | -0.0000 | -0.1255 | 22% | 0.36 |
| f_first_creator_sell | 49 | 48 | 30 | +0.0000 | -0.0001 | 28% | 1.00 |
| f2_creator_sell_incl_15s_net_seller | 54 | 48 | 25 | +0.0000 | -0.0335 | 28% | 0.62 |
| g_tp30_or_trail20_or_5m | 55 | 55 | 17 | +0.0000 | +0.0154 | 20% | 1.00 |
| g2_tp30_or_trail20_or_2m | 60 | 49 | 18 | +0.0000 | -0.0394 | 23% | 0.34 |
| g3_tp50_or_trail20_or_5m | 57 | 52 | 18 | +0.0000 | +0.1463 | 20% | 0.70 |
| g4_tp30_or_trail15_or_5m | 53 | 60 | 14 | +0.0000 | +0.0302 | 20% | 0.57 |
| g5_tp30_or_trail15_or_2m | 59 | 54 | 14 | +0.0000 | -0.0171 | 22% | 0.71 |
| h_tp100_or_trail30_or_5m | 70 | 42 | 15 | +0.0009 | +0.4168 | 18% | 0.01 |
| h2_tp100_or_trail30_or_15m | 69 | 41 | 17 | +0.0003 | +0.4594 | 18% | 0.01 |
| h3_tp100_or_trail30_or_30m | 68 | 42 | 17 | +0.0003 | +0.3690 | 18% | 0.02 |
| h4_tp300_or_trail30_or_30m | 66 | 42 | 19 | +0.0001 | +0.0401 | 17% | 0.03 |

### flow_v2/6 (n=21)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 6 | 6 | 9 | +0.0000 | -0.0091 | 98% | 1.00 |
| b2_paper_full_set | 6 | 1 | 14 | +0.0000 | -0.0021 | 98% | 0.12 |
| c_trail15 | 7 | 11 | 3 | -0.0000 | -0.0135 | 69% | 0.48 |
| c_trail30 | 6 | 12 | 3 | -0.0011 | -0.0714 | 95% | 0.24 |
| c_trail50 | 4 | 13 | 4 | -0.0011 | -0.1280 | 100% | 0.05 |
| d_arm+25%_trail30 | 4 | 13 | 4 | -0.0011 | -0.0850 | 100% | 0.05 |
| d_arm+50%_trail30 | 4 | 13 | 4 | -0.0011 | -0.0851 | 100% | 0.05 |
| d_arm+100%_trail30 | 3 | 14 | 4 | -0.0011 | -0.1091 | 100% | 0.01 |
| d_arm+25%_trail15 | 5 | 11 | 5 | -0.0000 | -0.0602 | 90% | 0.21 |
| d_arm+50%_trail15 | 5 | 12 | 4 | -0.0011 | -0.0672 | 90% | 0.14 |
| d_tp+25%_else_trail30 | 6 | 12 | 3 | -0.0011 | -0.0787 | 96% | 0.24 |
| d_tp+50%_else_trail30 | 5 | 13 | 3 | -0.0011 | -0.1049 | 100% | 0.10 |
| d_tp+100%_else_trail30 | 6 | 11 | 4 | -0.0000 | -0.0689 | 94% | 0.33 |
| e_time2m | 8 | 9 | 4 | +0.0000 | -0.0608 | 77% | 1.00 |
| e_time5m | 5 | 14 | 2 | -0.0011 | -0.1468 | 96% | 0.06 |
| e_time15m | 4 | 14 | 3 | -0.0011 | -0.1290 | 100% | 0.03 |
| e_time30m | 3 | 14 | 4 | -0.0011 | -0.1309 | 100% | 0.01 |
| f_first_creator_sell | 4 | 8 | 9 | +0.0000 | -0.0901 | 100% | 0.39 |
| f2_creator_sell_incl_15s_net_seller | 7 | 9 | 5 | +0.0000 | -0.1205 | 89% | 0.80 |
| g_tp30_or_trail20_or_5m | 6 | 13 | 2 | -0.0011 | -0.0607 | 86% | 0.17 |
| g2_tp30_or_trail20_or_2m | 7 | 12 | 2 | -0.0011 | -0.0675 | 91% | 0.36 |
| g3_tp50_or_trail20_or_5m | 6 | 13 | 2 | -0.0011 | -0.0790 | 86% | 0.17 |
| g4_tp30_or_trail15_or_5m | 5 | 13 | 3 | -0.0011 | -0.0466 | 87% | 0.10 |
| g5_tp30_or_trail15_or_2m | 7 | 11 | 3 | -0.0002 | -0.0474 | 87% | 0.48 |
| h_tp100_or_trail30_or_5m | 7 | 11 | 3 | -0.0000 | -0.0804 | 88% | 0.48 |
| h2_tp100_or_trail30_or_15m | 6 | 11 | 4 | -0.0000 | -0.0672 | 90% | 0.33 |
| h3_tp100_or_trail30_or_30m | 6 | 11 | 4 | -0.0000 | -0.0689 | 94% | 0.33 |
| h4_tp300_or_trail30_or_30m | 7 | 11 | 3 | -0.0000 | -0.0184 | 92% | 0.48 |

### flow_v2/8 (n=22)
| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |
|---|---|---|---|---|---|---|---|
| b_line_broken(2) | 6 | 11 | 5 | -0.0001 | -0.0187 | 88% | 0.33 |
| b2_paper_full_set | 7 | 4 | 11 | +0.0000 | +0.0032 | 74% | 0.55 |
| c_trail15 | 8 | 12 | 2 | -0.0004 | -0.0388 | 75% | 0.50 |
| c_trail30 | 5 | 15 | 2 | -0.0013 | -0.0883 | 96% | 0.04 |
| c_trail50 | 3 | 17 | 2 | -0.0030 | -0.1396 | 100% | 0.00 |
| d_arm+25%_trail30 | 2 | 18 | 2 | -0.0038 | -0.1279 | 100% | 0.00 |
| d_arm+50%_trail30 | 2 | 18 | 2 | -0.0038 | -0.1280 | 100% | 0.00 |
| d_arm+100%_trail30 | 2 | 18 | 2 | -0.0038 | -0.1280 | 100% | 0.00 |
| d_arm+25%_trail15 | 3 | 16 | 3 | -0.0019 | -0.1031 | 100% | 0.00 |
| d_arm+50%_trail15 | 3 | 17 | 2 | -0.0030 | -0.1102 | 100% | 0.00 |
| d_tp+25%_else_trail30 | 5 | 15 | 2 | -0.0011 | -0.0930 | 96% | 0.04 |
| d_tp+50%_else_trail30 | 4 | 16 | 2 | -0.0019 | -0.1383 | 100% | 0.01 |
| d_tp+100%_else_trail30 | 5 | 14 | 3 | -0.0011 | -0.0859 | 96% | 0.06 |
| e_time2m | 5 | 14 | 3 | -0.0017 | -0.0949 | 93% | 0.06 |
| e_time5m | 4 | 18 | 0 | -0.0050 | -0.1674 | 99% | 0.00 |
| e_time15m | 3 | 18 | 1 | -0.0038 | -0.1497 | 100% | 0.00 |
| e_time30m | 2 | 18 | 2 | -0.0038 | -0.1498 | 100% | 0.00 |
| f_first_creator_sell | 4 | 10 | 8 | +0.0000 | -0.0957 | 97% | 0.18 |
| f2_creator_sell_incl_15s_net_seller | 7 | 12 | 3 | -0.0012 | -0.1342 | 96% | 0.36 |
| g_tp30_or_trail20_or_5m | 7 | 14 | 1 | -0.0011 | -0.0853 | 78% | 0.19 |
| g2_tp30_or_trail20_or_2m | 9 | 11 | 2 | -0.0001 | -0.0823 | 76% | 0.82 |
| g3_tp50_or_trail20_or_5m | 6 | 15 | 1 | -0.0013 | -0.1191 | 83% | 0.08 |
| g4_tp30_or_trail15_or_5m | 7 | 13 | 2 | -0.0009 | -0.0729 | 80% | 0.26 |
| g5_tp30_or_trail15_or_2m | 9 | 10 | 3 | +0.0000 | -0.0715 | 78% | 1.00 |
| h_tp100_or_trail30_or_5m | 6 | 14 | 2 | -0.0011 | -0.0988 | 93% | 0.12 |
| h2_tp100_or_trail30_or_15m | 5 | 14 | 3 | -0.0011 | -0.0859 | 96% | 0.06 |
| h3_tp100_or_trail30_or_30m | 5 | 14 | 3 | -0.0011 | -0.0859 | 96% | 0.06 |
| h4_tp300_or_trail30_or_30m | 6 | 14 | 2 | -0.0011 | -0.0353 | 97% | 0.12 |
