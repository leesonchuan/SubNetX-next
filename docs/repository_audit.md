# SubNetX 仓库静态审计

审计日期：2026-07-08

审计范围：当前本地仓库 `SubNetX-next`。本次仅做静态阅读与检索，未运行科学流程、未运行测试、未修改现有源代码、未提交、未推送。

依据根目录 `AGENTS.md`，当前阶段目标是复现原始 SubNetX；暂时不修改科学算法；后续目标才是开发新的代谢途径发现与排序模型。因此本文只记录结构、流程、依赖、风险和复现准备项，不给出算法改动建议。

## 1. 仓库总体架构

仓库分成两个主要阶段：

| 目录 | 作用 | 备注 |
| --- | --- | --- |
| `1_subnetwork_extraction/` | 从 ARBRE/LCSB 网络中抽取目标化合物相关子网络，并生成优化阶段输入 | 核心代码在 `code/`；项目输入输出在 `projects/`；默认参数和排除列表在 `defaults/`；包含若干分析脚本 |
| `2_subentwork_analysis/` | 将抽取出的子网络整合进宿主模型，执行 FBA、TFA/MILP、路径枚举、最小路径和排序 | 目录名为 `subentwork`，看起来是原始拼写；核心包为 `subnetx/`，流程脚本在 `work/`，论文/示例脚本在 `tutorials/` |
| `tutorials/` | 两阶段下均存在教程或论文复现实例 | 第二阶段教程偏 E. coli 示例和绘图/打分 |
| `data/` | 两阶段各自的数据输入、词典、目标表、热力学数据、数据库辅助脚本 | 存在需要 Git LFS 或外部获取的数据风险 |
| `models/` | 第二阶段宿主 COBRA/TFA 模型 | 包含 `iJO1366.json`、`Yeast8.json`、`ecoliTFA.json`、`yeastTFA.json` 等路径引用 |

整体数据流：

```text
项目参数/目标化合物/ARBRE 网络
  -> 1_subnetwork_extraction/code/Main.py
  -> 图构建、前体过滤、路径扩展、收敛剪枝
  -> output_optimization_input/{compounds.tsv,reactions.tsv,molfiles/}
  -> 2_subentwork_analysis/work/add_subnet.py 或 tutorials/addSubnetEcoli.py
  -> subnetx 解析、宿主模型整合、FBA/TFA
  -> MILP 路径枚举、最小子网络、外部 ID 回填、最终表
```

## 2. 完整流程

### 2.1 子网络提取

入口是 `1_subnetwork_extraction/code/Main.py`。

1. `Data` 读取项目名、参数、化合物表、反应表、网络边表、反应平衡表、排除列表和可选宿主模型代谢物列表。
2. `Balance` 在缺少 `reaction_balance.csv` 时用 RDKit 从 SMILES 估算元素组成并检查反应两侧元素计数。
3. `compoundFiltering` 过滤候选前体，要求含碳，可选择按结构片段过滤。
4. `Graph` 从 `Network.csv` 或缓存的 gpickle 构建 NetworkX 无向图，节点为化合物，边表示可连接两个化合物的反应集合。
5. `Extraction` 先找目标到前体的短路径，再按外边界继续扩展，生成逐轮子网络。
6. `Convergence` 删除仍有外部边界的边和孤立组分，生成收敛后的子网络。
7. `Format` 将收敛子网络转换为第二阶段需要的 `reactions.tsv`、`compounds.tsv` 和 molfile。

需要注意：静态代码显示 `Balance` 当前没有检查电荷，也会在比较元素守恒时移除氢；这与 `AGENTS.md` 对后续新增反应的约束不同。复现阶段不应直接改变该原始行为，但后续新增反应必须额外检查元素守恒、化学计量守恒和电荷。

### 2.2 宿主模型整合、FBA 和 TFA

主要入口为 `2_subentwork_analysis/work/add_subnet.py`，教程版入口为 `2_subentwork_analysis/tutorials/addSubnetEcoli.py` 和 `thermoModelbuilder.py`。

1. `subnetx.io.parser.input_parser_netw()` 读取第一阶段输出的 `compounds.tsv` 和 `reactions.tsv`。
2. `load_model()` / `load_tmodel()` 加载宿主模型，当前支持 E. coli `iJO1366` 和 yeast `Yeast8`。
3. `ChassisModel` 将 COBRA/pytfa 模型包装为带有 `met_lexicon` 和 `rxn_lexicon` 的宿主模型。
4. `integrate_network()` / `integrate_pathway()` 添加异源代谢物、异源反应、边界需求反应和目标产物 demand reaction。
5. FBA 使用 COBRA/TFA 模型的 `slim_optimize()` 检查目标产物是否可产生。
6. 若开启热力学评价且 FBA 可行，则加载 TFA 模型，调用 `prepare()`、`convert()`，并用 GUROBI/CPLEX 接口求解。

### 2.3 MILP、路径枚举、热力学评价和路径排序

1. `enumerate_subnets.py` 对整合后的模型添加 `ForwardBackwardUseVariable` 二元变量和耦合约束，枚举可行异源子网络，并用 integer cut 排除已找到方案。
2. `find_minimal_subnets.py` 先最大化目标产物，再固定产量阈值，最小化二元变量数量，枚举最小子网络。
3. `extract_min_pathways.py` 从 MILP 解中提取激活的异源反应集合。
4. `ext_ids_min_path.py` 用 `rxn_lexicon` 将内部反应 ID 映射回 LCSB ID。
5. `prepare_final_table.py` 汇总 reaction/metabolite 表、枚举结果、最小路径和外部 ID，生成 `final_table.csv`。
6. `subnetx.core.analysis.thermo_evaluation()` 与教程中的 `collect_scores.py` 负责更完整的热力学数据构建、TFA 可行性和 BridgIT 分数/产率等排序指标。

## 3. 主要 Python 文件功能

### 3.1 `1_subnetwork_extraction/code`

| 文件 | 功能 |
| --- | --- |
| `Main.py` | 第一阶段总入口，串联数据读取、平衡检查、前体过滤、图构建、扩展、收敛和格式化输出 |
| `Data.py` | 读取参数、项目目录、网络/反应/化合物表、排除列表、辅助网络和宿主模型代谢物 |
| `Balance.py` | 基于 RDKit 解析 SMILES，生成化合物原子组成并检查反应元素平衡 |
| `Compound.py` | 前体筛选、RDKit 片段匹配、MCS 相似度、前体候选识别 |
| `Subnetwork.py` | NetworkX 图构建、最短路径、边/节点注释、外边界识别、统计与 Gephi 输出 |
| `Extraction.py` | 初始路径和逐轮边界扩展，使用 multiprocessing 查找候选连接路径 |
| `Convergence.py` | 对扩展网络做收敛剪枝，删除未闭合边界和孤立组分 |
| `Format.py` | 将收敛子网络写成第二阶段输入，并调用 Open Babel 生成 molfile |

### 3.2 `1_subnetwork_extraction/analyses`

| 文件 | 功能 |
| --- | --- |
| `NICEpathwaysCoverage.py` | 静态看是围绕 NICEpathways/抽取覆盖情况的分析入口 |
| `check_matching_EC_8_compounds.py` | 检查 EC 8 类化合物匹配情况 |
| `plotNetworkExtractionRoundsStats.py` | 绘制网络抽取轮次统计图 |
| `plotOptimisationNumReactionsInTop10.py` | 绘制优化结果中 top 10 反应数量统计 |

### 3.3 `2_subentwork_analysis/subnetx`

| 文件 | 功能 |
| --- | --- |
| `subnetx/core/chassis.py` | `ChassisModel`，继承/包装 `pytfa.core.model.LCSBModel`，负责添加异源代谢物、反应、边界反应和目标反应 |
| `subnetx/core/integration.py` | 将单一路径或整张网络整合进宿主模型，支持分支路径 |
| `subnetx/core/analysis.py` | 热力学数据库补充、新反应整合、TFA 模型构建和策略评估 |
| `subnetx/core/ranking.py` | MILP 二元变量、耦合约束、intermediate bias 和 integer cut |
| `subnetx/io/parser.py` | 解析 `compounds.tsv`、`reactions.tsv`、`pathways.tsv`、`pathways_branching.tsv`，生成代谢物/反应/路径字典 |
| `subnetx/io/json.py` | JSON 模型保存和读取包装 |
| `subnetx/io/dict.py` | COBRA/TFA/ChassisModel 的 dict 序列化和反序列化 |
| `subnetx/optim/constraints.py` | 自定义 optlang/pytfa 约束类，包括 integer cut 和上下界耦合 |
| `subnetx/optim/variables.py` | 当前为空的变量扩展模块 |
| `subnetx/utils/utils.py` | 阻断反应检测、KEGG 分子量查询等工具 |
| `subnetx/thermo/thermodb.py` | eQuilibrator/LocalCompoundCache 热力学数据库构建与合并 |
| `__init__.py` 文件 | 导出核心、IO、优化和工具模块 |

### 3.4 `2_subentwork_analysis/work`

| 文件 | 功能 |
| --- | --- |
| `add_subnet.py` | 主整合脚本，支持 E. coli 和 yeast，构建子网络整合模型并输出 FBA/TFA 评价 |
| `eval_netws.py` | 遍历目标化合物目录并调用 `model_builder()` 做网络评价 |
| `enumerate_subnets.py` | 对整合模型枚举可行异源子网络 |
| `find_minimal_subnets.py` | 在产量阈值约束下寻找最小反应数子网络 |
| `extract_min_pathways.py` | 从 MILP 解表提取激活反应列表 |
| `ext_ids_min_path.py` | 将内部异源反应 ID 转换为外部 LCSB ID |
| `prepare_final_table.py` | 汇总候选网络、最小路径、外部 ID 和原始反应/化合物信息 |

### 3.5 `2_subentwork_analysis/tutorials`

| 文件 | 功能 |
| --- | --- |
| `addSubnetEcoli.py` | E. coli 专用整合和 FBA/TFA 示例 |
| `thermoModelbuilder.py` | 对 E. coli/yeast 路径逐条构建模型并做 FBA/TFA 评价 |
| `eval_netws.py` | 教程数据集网络评价入口 |
| `enumerate_subnets.py` | 教程版子网络枚举 |
| `find_minimal_subnets.py` | 教程版最小子网络搜索 |
| `find_high_score.py` | 按 BridgIT 分数偏置搜索高分路径 |
| `bias_intermediates.py` | 按指定中间体偏置 MILP 搜索 |
| `extract_pathways.py` | 从枚举结果提取路径反应集合 |
| `extract_min_pathways.py` | 从最小子网络结果提取路径 |
| `extract_biased_pathways.py` | 从偏置搜索结果提取路径 |
| `ext_ids_min_path.py` | 教程版 LCSB ID 回填 |
| `eval_pthws.py` | 路径级评价脚本 |
| `find_shiki_target.py` | shikimate 相关目标/中间体打分分析 |
| `collect_scores.py` | 汇总产率、BridgIT 分数和热力学可行性 |
| `get_max_yield.py` | 计算目标在不同宿主中的最大产率/克产率 |
| `prep_plot.py` | 准备绘图用 Excel 表 |
| `do_plots.py` | 生成论文/教程图 |
| `conv_thermodata.py` | 将 MATLAB 热力学数据转换为 pytfa 可读格式 |
| `thermoDBconverter.py` | 热力学数据库 `.mat` 到 Python pickle/zlib 格式转换工具 |

### 3.6 `2_subentwork_analysis/data/get_data`

| 文件 | 功能 |
| --- | --- |
| `connect_to_DB.py` | 连接 LCSB MySQL 数据库并查询化合物/反应 ID |
| `find_LCSB_id_rxns.py` | 为 E. coli 反应查找 LCSB ID |
| `find_LCSB_id_rxns_yeast.py` | 为 yeast 反应查找 LCSB ID |
| `get_LCSBID4targets.py` | 为目标化合物查找 LCSB ID |

## 4. 依赖和外部软件

静态导入和配置中可见的 Python 依赖：

- `pandas`、`numpy`、`matplotlib`、`scipy`
- `networkx`
- `rdkit`
- `cobra`
- `pytfa`
- `optlang`
- `openbabel` Python 绑定
- `equilibrator_api`、`equilibrator_assets`、`equilibrator_cache`
- `requests`
- `tqdm`
- `mysql-connector-python`
- `setuptools`
- 标准库：`os`、`sys`、`json`、`pickle`、`zlib`、`multiprocessing`、`hashlib`、`itertools`、`warnings` 等

外部软件和服务：

- Open Babel CLI：`Format.py` 调用 `obabel` 生成 molfile。
- MILP solver：脚本默认使用 `optlang-gurobi`，也定义了 `optlang-cplex`。
- Git LFS：README 提到需要 `git lfs pull` 获取数据。
- LCSB MySQL 数据库：`connect_to_DB.py` 硬编码数据库连接信息。
- KEGG REST：`utils.get_molecular_weight()` 查询 KEGG compound。
- eQuilibrator/Zenodo/local compound cache：热力学数据库构建依赖。
- Gephi：第一阶段可输出 `.gexf` 供可视化。

## 5. 数据输入和输出格式

### 5.1 第一阶段输入

- `1_subnetwork_extraction/data/Network.csv`：网络边表，代码读取 `UID of pair`、`score`、`UID of reaction`、`UID of source`、`UID of target`、`M_PR_UID` 等列。
- `1_subnetwork_extraction/data/Reactions.csv`：反应表，包含 LCSB/ARBRE 反应 ID、反应物、产物、方向、酶、分数等字段。
- `1_subnetwork_extraction/data/Compounds.csv`：化合物表，包含 LCSB/ARBRE 化合物 ID、名称、SMILES/InChIKey 等字段。
- `1_subnetwork_extraction/data/reaction_balance.csv` 和 `compound_atoms.json`：反应元素平衡和化合物原子组成缓存。
- `1_subnetwork_extraction/defaults/parameters.txt` 与 `projects/<project>/parameters.txt`：参数文件。
- `1_subnetwork_extraction/defaults/excludelists/*`：化合物、反应、pair、主反应等排除列表。
- `1_subnetwork_extraction/data/auxilary_network/*`：可选辅助网络。
- `projects/<project>/model_mets.txt`：可选宿主模型已有代谢物列表。

### 5.2 第一阶段输出

- `projects/<project>/stats/*`：抽取和收敛统计。
- `projects/<project>/figures/*`：统计图。
- `projects/<project>/auxilary_output/*`：边界、反应 ID、中间网络文件。
- `projects/<project>/output_optimization_input/reactions.tsv`：第二阶段反应输入。
- `projects/<project>/output_optimization_input/compounds.tsv`：第二阶段化合物输入。
- `projects/<project>/output_optimization_input/molfiles/*.mol`：Open Babel 生成的 molfile。
- 可选 `subnetwork.gexf` 等图文件。

### 5.3 第二阶段输入

- `compounds.tsv`、`reactions.tsv`：由第一阶段输出。
- 可选 `pathways.tsv`、`pathways_branching.tsv`：路径级评价需要。
- `2_subentwork_analysis/models/*.json`：宿主 COBRA/TFA 模型。
- `2_subentwork_analysis/data/LCSBids_*.csv`、`rxn_LCSBID_*.csv`、`target_LCSBID.csv`：宿主模型与 LCSB ID 映射。
- `2_subentwork_analysis/data/Compound-precursor.xlsx`：目标和前体/主 hub 关系。
- `2_subentwork_analysis/data/bridgit_predictions.csv`：教程高分路径排序。
- `data/thermo_data.thermodb` 或教程中的 `thermodata_*.thermodb`：热力学数据库。

### 5.4 第二阶段输出

- `Model_<target>.json` 或宿主模型名组合的 JSON 模型。
- `network_eval_<organism>.csv`：整张网络 FBA/TFA 评价。
- `pathway_eval_<organism>.csv`：路径级 FBA/TFA 评价。
- `enumerated_subnets.csv`：枚举子网络。
- `minimal_subnets_<threshold>_production.csv`：最小子网络。
- `pthws_info_<threshold>_min.csv`：最小路径反应列表。
- `pthws_ids_<threshold>_min.csv`：外部 ID 路径表。
- `final_table.csv`、`final_scores.csv`、绘图 Excel/图像文件。

## 6. 硬编码路径、化合物 ID 和宿主设置

| 类型 | 位置 | 静态发现 |
| --- | --- | --- |
| 相对路径 | 多数脚本 | 大量使用 `../data`、`../models`、`../projects`、`results_processed`、`results_processed-master/EPFL`，要求从特定工作目录运行 |
| 目标 | `work/eval_netws.py` 等 | 当前主流程默认 target list 中可见 `Aklavinone` |
| 宿主 | `work/add_subnet.py`、`tutorials/thermoModelbuilder.py` | 支持 `ecoli`、`yeast`；默认流程中 `organism = 'yeast'`，教程 E. coli 脚本中 `ORGANISM = 'ecoli'` |
| E. coli 模型 | `add_subnet.py`、`addSubnetEcoli.py` | `iJO1366.json`、`ecoliTFA.json`、`EX_glc__D_e`、`BIOMASS_Ec_iJO1366_WT_53p95M`、`EX_co2_e` |
| Yeast 模型 | `add_subnet.py`、`thermoModelbuilder.py` | `Yeast8.json`、`yeastTFA.json`、`r_1714`、`r_4041`、`r_1672` |
| 化合物 ID | `Compound.py` | `383753545 -> 1467865652` 作为硬编码的 CoA/methyl-CoA 特例 |
| 离子/边界排除 | `Subnetwork.py` | `1467865652`、`1467880389`、`1469319694` 等被硬编码排除 |
| 数据库 | `data/get_data/connect_to_DB.py` | 硬编码 LCSB MySQL 主机、用户名和密码；本文不复述密码 |
| solver | 多个第二阶段脚本 | 默认 `solver = 'optlang-gurobi'`，CPLEX 只作为常量存在 |
| 热力学数据 | `analysis.py`、`collect_scores.py` | `data/thermo_data.thermodb`、`results_processed-master/EPFL/thermo_all/thermodata_ecoli.thermodb` |

## 7. 可能存在的 bug 和风险优先级

### P0

1. `2_subentwork_analysis/work/add_subnet.py` 中 `preprocess_model(model, org)` 定义需要两个参数，但 `model_builder()` 调用为 `preprocess_model(cobra_model)`。这会导致主 `work/` 版本在执行到该处时抛出参数错误。需要运行验证。
2. `2_subentwork_analysis/subnetx/io/parser.py` 中 `met_parser()` 对 `KEGG2SEED_update.xlsx` 使用 `open(filename, 'rb')`，随后却按 DataFrame 方式索引 `kegg2seed[...]`。如果触发 KEGG 注释分支，应会失败。需要运行验证触发条件。
3. `2_subentwork_analysis/subnetx/io/dict.py` 的模型序列化中，代谢物热力学信息写入调用疑似把 `rxn_dict` 传给了代谢物辅助函数，可能污染或丢失 JSON 字段。需要运行验证。
4. `2_subentwork_analysis/data/get_data/connect_to_DB.py` 包含硬编码数据库凭据。即使复现阶段不使用该脚本，也属于高优先级安全和可复现性风险。
5. 当前本地 Git 工作区存在大量预先存在的 staged 删除和未跟踪同名文件状态；这不是源码 bug，但在提交前属于 P0 流程风险，应先单独清理或重新确认，避免把导入异常提交到 GitHub。

### P1

1. `Data.py` 虽然记录默认参数文件，但随后直接读取 `../projects/<project>/parameters.txt`；如果项目缺少参数文件，默认参数是否能生效需要运行验证。
2. `Data.py` 的项目目录创建使用相对路径，若 `../projects` 不存在可能失败。需要运行验证。
3. `Subnetwork.py` 中判断网络缓存路径的条件写成 `os.path.exists(self.data.network_file and os.path.exists(...))`，混合了字符串和布尔值，逻辑可疑。需要运行验证。
4. `Balance.py` 的平衡检查移除氢且不检查电荷；对于后续新增反应不满足 `AGENTS.md` 的科学约束。
5. `Data.processNewReactions()` 将辅助反应直接标记为 `balance=1`，静态代码中未见元素/电荷重新验证。
6. `Data.processNewCompound()` 对新增化合物填入 `LD50_mg_kg=10000` 等默认值，并存在 pandas membership 判断可疑；不能在科学结果中把这些当真实数据。
7. `parser.py` 的输入列名约定和第一阶段输出列名可能不完全一致，例如 SMILES 字段常量与 `Format.py` 输出字段需要运行验证。
8. `parser.py` 在缺少注释时生成 `fakeID_*` seed 注释；后续报告必须明确这是占位符，不能当真实代谢物注释。
9. `subnetx/core/analysis.py` 中当传入对象已经是 `ThermoModel` 时，后续是否仍正确设置 `tmodel` 需要运行验证。
10. `Format.py` 调用 `os.system('obabel ...')` 不检查返回码，路径中有空格时也可能失败。
11. 第二阶段默认依赖 GUROBI；若 AutoDL 没有 license 或 optlang-gurobi，MILP/TFA 会失败。
12. `find_minimal_subnets.py` 将大边界从 `+-1000` 收紧到 `+-50`，这会影响可行空间；复现时需要确认这是原始流程设定而不是后续改动。

### P2

1. 大量脚本依赖当前工作目录，直接从仓库根目录运行可能找不到 `../data`、`../models` 或 `results_processed`。
2. `multiprocessing.Pool()` 没有显式进程数，Windows 下 spawn 开销和资源占用需要运行验证。
3. `Extraction.py` 中 `pool.close()` 后未显式 `pool.join()`，是否造成资源未释放需要运行验证。
4. `Format.py` 模块级 `createMolfiles()` 对已生成 molfile 的检查看的是 `output_optimization_input_dir` 而不是 `molfiles` 子目录，可能重复生成。需要运行验证。
5. `Compound.py` 中片段目录使用 `../precursor_patterns/<cmp_name>/`，而仓库默认片段位于 `defaults/precursor_patterns`，路径是否有效需要运行验证。
6. `utils.get_molecular_weight()` 在 KEGG ID 缺失或请求失败时返回 `100`，这是占位值，不能用于严肃产率结论。
7. `extract_min_pathways.py` 使用 `DataFrame.iteritems()`，在 pandas 2.x 中存在兼容性风险。
8. `Subnetwork.py` 全局关闭 pandas chained assignment warning，可能隐藏数据写入问题。
9. `Data.py` 在未提供项目名时调用 `input()`，不适合非交互 AutoDL 批处理。
10. 仓库内存在 `dist/*.egg`、`__pycache__`、运行结果目录等历史产物；后续提交前需要按 `.gitignore` 和 `AGENTS.md` 清理策略确认。

## 8. Windows 与 Linux 兼容性问题

- 路径分隔符大多由字符串拼接和相对路径组成，Windows 可读但高度依赖启动目录；Linux/AutoDL 上也必须从脚本预期目录运行。
- Open Babel CLI 名称在代码中写为 `obabel`，Windows 和 Linux 都需要确认命令可用且在 `PATH` 中。
- RDKit、Open Babel Python 绑定、pytfa、COBRApy、GUROBI 在 Windows 本地安装难度较高；正式运行更适合 Linux/conda 环境。
- `multiprocessing` 在 Windows 使用 spawn，第一阶段扩展可能比 Linux 慢且更容易暴露 pickling 问题；需要运行验证。
- `connect_to_DB.py` 依赖外部数据库主机和网络访问；AutoDL 防火墙/网络策略可能阻断。
- `git lfs pull` 和大数据下载在网络受限环境下需要提前准备。

## 9. 版本风险

| 组件 | 风险 |
| --- | --- |
| NetworkX | 代码使用 `nx.write_gpickle()` / `nx.read_gpickle()`；NetworkX 3.x 顶层 gpickle API 兼容性需要确认。最短路径和子图 view 行为也可能影响旧代码。 |
| RDKit | SMILES 解析、分子式、fragment/MCS 行为可能随版本变化；平衡检查和前体过滤结果需要固定版本复现。 |
| COBRApy | JSON 模型、reaction/metabolite API、solver 配置和 `slim_optimize()` 行为随版本变化；需确认与 pytfa 兼容版本。 |
| pytfa | 对 COBRApy、optlang、solver 接口高度敏感；自定义 JSON 序列化也依赖 pytfa 内部字段。 |
| Open Babel | CLI `obabel` 和 Python `openbabel` 绑定安装方式差异大；molfile 生成失败会影响热力学和注释流程。 |
| pandas | `iteritems()`、`append()`、`astype('Int64')`、Excel engine 默认值等在 pandas 2.x 存在兼容性风险。 |
| GUROBI/CPLEX/optlang | 求解器接口、license、容差字段名不同；教程中既有 `solver.configuration.tolerances.feasibility`，也有 `solver.problem.Params.FeasibilityTol`。 |
| eQuilibrator | `equilibrator_api`、`equilibrator_cache`、`equilibrator_assets` 与本地 sqlite/Zenodo 数据源版本需要锁定。 |

## 10. 缺少的测试

静态检查未发现系统化测试目录或 CI 配置。建议后续新增测试时优先覆盖：

- 第一阶段参数读取和项目目录解析。
- `Balance` 对元素、电荷、化学计量的最小样例。
- `Compound` 前体过滤和 fragment 路径解析。
- `Graph` 构建、gpickle 缓存读取、外边界识别。
- 第一阶段输出 `compounds.tsv` / `reactions.tsv` 与第二阶段 parser 的契约测试。
- `ChassisModel` 添加代谢物、反应、边界和目标 demand reaction。
- FBA 最小 smoke test，使用极小模型避免依赖 GUROBI。
- TFA/MILP solver 可用性检测和失败时的清晰错误。
- JSON 序列化/反序列化 round trip。
- `work/` 主流程 ajmalicine/Aklavinone 目标的静态路径存在性和输入文件检查。

## 11. AutoDL 复现 ajmalicine 示例准备工作

以下只基于静态代码推导，具体命令和版本需要先在 AutoDL 上小规模验证。

1. 确认目标名称在当前数据中如何命名。`work/eval_netws.py` 静态可见目标为 `Aklavinone`；如果要复现 ajmalicine，需要确认 `results_processed`、`Compound-precursor.xlsx`、`target_LCSBID.csv` 中是否存在 `Ajmalicine` 或对应 LCSB ID。需要运行验证。
2. 准备 Linux conda 环境，固定 Python、RDKit、NetworkX、pandas、COBRApy、pytfa、optlang、Open Babel、eQuilibrator 相关包版本。
3. 安装 Open Babel CLI，并确认 `obabel` 可执行。
4. 准备 GUROBI 或 CPLEX license；若只做 FBA smoke test，可先确认 COBRApy 默认 solver 是否可用。
5. 执行 `git lfs pull` 或手动确认大数据、模型、热力学数据库文件完整。
6. 确认第一阶段项目目录下存在目标参数文件、目标/前体定义、`output_optimization_input` 预期输出目录。
7. 先只跑第一阶段最小目标，检查 `reactions.tsv`、`compounds.tsv`、`molfiles/` 是否生成且 parser 可读。
8. 在第二阶段从 `2_subentwork_analysis/work` 目录运行脚本，避免相对路径失效。
9. 先关闭热力学评价做 FBA smoke test，再开启 TFA/MILP。
10. 在正式结果前记录所有命令、环境版本、solver、输入文件 checksum 和输出文件路径。

## 12. 本次静态审计运行的命令和测试结果

已运行的静态读取/检索命令包括：

- `Get-Content -Encoding UTF8 AGENTS.md`
- `rg --files`
- `rg --files -g "*.py"`
- `Get-Content -Encoding UTF8 <核心 Python 文件>`
- `rg -n ...` 检索函数、类、I/O、硬编码路径和脚本入口
- `Get-ChildItem -Recurse -Filter *.py | Select-String ...` 检索导入依赖

测试结果：

- 未运行单元测试。
- 未运行第一阶段抽取。
- 未运行 FBA、TFA、MILP 或热力学评价。
- 未执行任何提交或推送。

