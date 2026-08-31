# SenSec 机理图模块

该目录实现 SenseCLLM 的物理机理图分析和实验参数生成，是 MechanismAgent、
VulnerabilityAgent 与 ExperimentAgent 使用的领域模块。

当前执行语义：

- Step 2 优先生成一到两个有目标设备依据的机理；如果 local component、reachable
  modality 和 physical operation 不能同时得到支持，则允许不生成候选。
- Step 3 通过 `use_verifier=False` 执行 forward reasoning，主流程由独立 CriticAgent
  承担统一复核职责。
- Step 4 使用 generator 与 deterministic schema/range validation 生成实验验证方案。

该模块通过 run-scoped artifacts 与 Harness 交互；Agent runtime 负责 subprocess
isolation、checkpoint、retry、budget、event 和 trace。
