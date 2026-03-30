# **面向带格式文档（DOCX/DOC）的AI查重、AIGC检测与自动化降重技术的深度研究报告**

大型语言模型（Large Language Models, LLMs）的爆炸式发展从根本上重塑了学术研究、公文写作与代码开发的范式。随着生成式人工智能（AIGC）工具在各个领域的广泛渗透，学术界、出版界与企业合规部门正面临着前所未有的内容治理危机。生成式模型不仅能够以极其逼真的风格输出长篇学术论文，还能通过复杂的对抗性改写策略规避传统的文本审查机制。这一现象迫使全球的检测技术从传统的基于数据库比对的“查重（Plagiarism Detection）”迅速向基于统计学特征与深度学习特征的“AIGC检测（AI-Generated Content Detection）”演进。

在真实的业务与学术场景中，检测与降重的核心痛点往往并非自然语言处理模型本身的语义理解能力，而是如何处理带有复杂排版、引用、图表与跨页结构的带格式文档（如DOCX和DOC）。传统的文件处理方式倾向于将文档剥离为纯文本进行分析与重写，这会导致所有格式元数据（Metadata）的灾难性丢失，使得处理后的文本无法直接用于最终提交或发表。本报告对如何处理带格式文档的AI查重与AIGC检测进行了详尽的解构，并深入探讨了根据检测结果进行自动化降重及降低AIGC疑似率的底层逻辑与工程实现。通过整合前沿的自然语言处理技术、文档对象模型（DOM）解析策略以及对抗性提示词工程，本研究旨在为构建端到端、格式无损的自动化文档合规工作流提供理论基础与实践路径。

## **格式化文档（DOCX/DOC）的底层解析与无损重构机制**

在对学术论文或商业报告进行AI查重、AIGC检测及随后的降重处理时，首要的工程瓶颈是带格式文档的解析与重构。学术论文通常包含极其复杂的排版约定，包括多级标题、嵌套列表、浮动图表、行内公式以及特定格式的参考文献标记。如果采用常规的文本提取方案将文档降维为纯文本结构，随后的大语言模型改写将彻底摧毁文档的视觉与结构完整性。因此，深入理解DOCX格式的底层架构是实现自动化降重工作流的先决条件。

### **OpenXML架构与文档解析挑战**

DOCX文件并非许多人误以为的专有二进制数据块，其本质上是基于Microsoft Open XML规范（ISO/IEC 29500）的ZIP压缩文档包 1。将任何DOCX文件的后缀名修改为ZIP并进行解压，即可暴露出其内部错综复杂的XML文件层级结构。文档的核心语义结构与主体文本内容均存储于名为word/document.xml的主文件中，而样式、编号和媒体资源则分别存储在styles.xml、numbering.xml及media文件夹中 1。

在这个XML架构中，文档的每一个视觉与结构特征都由严格的层级标签所定义。例如，表格内容并非像PDF那样仅由绝对坐标定位的线段与文本组成，而是由明确的\<w:tbl\>标签定义，其内部嵌套了代表行的\<w:tr\>标签与代表单元格的\<w:tc\>标签 1。这种结构化的特性使得像LlamaParse这样的现代解析器能够直接从Word XML中提取表格内容，完美保留合并单元格（通过gridSpan和vMerge属性）、嵌套结构与超链接，这在解析PDF时是极难实现的 1。

在段落层面，文本由\<w:p\>标签包裹。段落内部并非单一的文本字符串，而是由多个运行块（Runs，标签为\<w:r\>）组成。运行块被定义为具有完全相同格式属性的连续文本区域 1。具体的文本字符存储于运行块内部的\<w:t\>标签中，而该段文本的格式属性（如加粗、斜体、删除线、下划线、上标、下标等）则被封装在\<w:rPr\>（Run Properties）属性标签中 1。

在进行AI自动化降重（即定位高AIGC疑似度文本并进行替换）时，系统面临的最大挑战是“运行块碎片化（Run Fragmentation）”6。在人类作者编辑文档的过程中，拼写检查的波浪线标记、修订跟踪记录（RSID，用于追踪不同作者在不同时间的编辑）以及后台的书签插入，都会导致一个在视觉上完全连贯的单词或句子被底层XML引擎强行切割进多个不同的运行块中 6。由于Python中的基础字符串（str）对象仅仅是字符的序列，无法对字体或排版信息进行编码，若算法直接提取段落的纯文本属性进行大语言模型改写，再将生成的纯文本字符串强行赋回给段落对象，将会彻底抹除该段落内所有的字符级格式。例如，原本用于标识物种学名的斜体、用于标识参考文献序号的上标，均会在赋值瞬间灰飞烟灭 4。

### **格式无损的文本映射与替换算法**

为了在应用大语言模型降重结果的同时绝对保留原有的排版格式与引文标注，算法必须深入到运行块（Run）甚至更细粒度的XML节点级别进行操作。基于Python生态的python-docx库或基于C\#的OpenXML SDK，前沿的格式无损替换策略通常遵循一套精密的节点映射机制。

首先，系统必须放弃在段落层级（paragraph.text）进行简单的字符串正则替换，转而遍历段落内的所有运行块集合（paragraph.runs）7。当检测到目标替换文本完整存在于单一运行块内时，可以直接修改该运行块的文本属性。然而，面对运行块碎片化问题，目标文本往往跨越了多个连续的运行块。此时，算法需要提取第一个包含该文本起始部分的运行块，将降重后生成的新文本注入该运行块的\<w:t\>标签中。随后，算法必须将承载原文本剩余部分的其他连续运行块的文本内容清空（即赋值为空字符串""），以此在不删除底层XML节点的前提下完成视觉层面的文本替换 8。

在某些更为高级的企业级实现中，例如借助C\#的OpenXML SDK，系统会采取属性克隆（Property Cloning）策略。算法首先捕获目标文本所在区域的RunProperties，随后清除段落下的旧有运行块节点。接着，利用降重后的新文本实例化全新的运行块，并将之前克隆的格式属性深拷贝并重新附加到新节点上，从而实现百分之百的样式继承与无缝融合 10。诸如python-docx-replace等专用的开源库，以及Vesence等专门针对Word文档构建原生解析引擎的商业平台，均采用了这种基于底层OOXML规范的映射机制。这种深度集成的策略确保了即便论文经过多轮大语言模型的彻底重写，其复杂的标题层级、项目符号的一致性、跨页的表格排版以及原生追踪的行内引用（Inline Citations）均能保持完好无损，直接输出达到出版级标准的成稿 8。

## **传统查重与前沿AIGC检测的算法机制深度剖析**

要针对性地降低学术论文的重复率与AI疑似度，必须在算法层面深刻理解这两种检测机制的根本差异。传统学术查重工具与现代AIGC检测器在数据依赖模式、特征提取逻辑与最终评估维度上存在着不可逾越的本质区隔。将应对传统查重的同义词替换策略直接应用于AIGC检测，往往会适得其反。

### **传统学术查重的比对机制与局限性**

传统查重系统（如Turnitin的Similarity Report机制、知网CNKI、Copyleaks的抄袭检测模块以及维普VPCS）的核心底层逻辑是“重合度或指纹匹配”14。这些系统的有效性完全建立在极其庞大的专有底层数据库之上，涵盖了数以亿计的已发表期刊论文、学术会议记录、互联网历史档案以及历年学生提交的作业库。

在算法实现上，传统查重工具通过提取输入文档的N-gram特征序列、计算局部敏感哈希值（Hash/Fingerprinting）或利用TF-IDF等自然语言处理技术，在庞大的数据库中进行高维度的相似性检索 14。这类系统主要针对“词汇与句子结构的直接物理复制”以及“浅层、低复杂度的同义词替换”。然而，随着大语言模型技术的爆发，AI能够根据极简的提示词对既有文献进行深度的句法重构与语义级别的彻底重塑（Paraphrasing）。大语言模型能够轻易改变句子结构、翻转主被动语态、重排段落逻辑，这导致基于字符串和哈希匹配的传统查重系统面对高质量的AI改写时形同虚设 14。这也是为何全球各大查重平台在2023年后被迫紧急研发并引入独立的AI检测模块的根本原因。

### **AIGC检测的核心统计学特征：困惑度与突发性**

与高度依赖外部数据库比对的抄袭检测截然不同，AIGC检测工具主要通过分析文本自身的内在统计学特征（Statistical Signatures）来判断其创作者的身份 19。在众多统计指标中，困惑度（Perplexity）与突发性（Burstiness）构成了当前检测算法最核心的评估基石 14。

困惑度（Perplexity, PPL）是自然语言处理领域用于评估语言模型预测样本能力的标准指标，它直观地反映了文本的“不可预测性”或系统在阅读该文本时的“惊讶程度”22。在数学定义上，给定一个词元（Token）序列，语言模型通过计算在给定前置上下文的情况下，生成每一个后续词元的概率。困惑度通常被定义为序列中所有词对数似然（Log-Likelihood）平均值的负指数。其形式化表示如下：

在给定分词器将字符序列解析为词元列表的前提下，语言模型输出词汇表上的概率分布，其对数困惑度（Log-Perplexity）为： ![][image1] 其中 ![][image2] 为文本中词元的总长度，而 ![][image3] 代表模型在已知前面所有词元的情况下，准确预测第 ![][image4] 个词元的概率 24。由于大语言模型在预训练与微调阶段的核心目标便是优化交叉熵损失，使其倾向于输出概率最高、最符合大众语言习惯的词序列，因此，未经特殊对抗性处理的AI生成文本通常具有极低的困惑度 21。换言之，AI的用词选择极其符合常规逻辑，极易被另一个语言模型预测。相反，人类作家在创作时充满创意、情感波动、独特的词汇搭配甚至偶尔的语法瑕疵，这种“随机性”使得人类文本的困惑度普遍较高 16。

突发性（Burstiness）则从宏观的篇章结构层面进行评估。它衡量的是文本在句子长度、句法结构复杂度和信息密度上的统计方差与同质性 23。机器生成的文本受限于其自回归生成机制，往往倾向于维持一个极其稳定且均匀的节奏，句子长度分布集中，结构四平八稳，缺乏起伏。而人类在写作时，受潜意识情绪、思维跳跃及表达焦点转移的影响，通常会在长篇大论的复杂复合句之后，突然插入一个极具冲击力的短句进行总结。这种“爆发与停顿”交替出现的动态变化，在统计学上即表现为高突发性 23。目前的检测工具正是通过综合评估文本的低困惑度与低突发性特征组合，来锁定AIGC内容的 19。

### **零样本检测法与监督分类模型的理论边界**

在具体的算法落地层面，当今的AIGC检测技术阵营主要分裂为基于监督学习的分类模型（Supervised Classifiers）与无需训练数据的零样本检测法（Zero-Shot Methods）。

监督学习检测器（如基于RoBERTa微调的模型、RADAR框架以及GhostBuster）通过输入海量带有明确标签的人类与AI生成文本进行二分类训练 28。尽管这类模型在与其训练集数据分布一致（In-Distribution）的测试中表现出极高的准确率，但其实际应用中面临着严重的“分布外（Out-of-Distribution, OOD）鲁棒性”危机 28。当面对未参与其训练的全新大语言模型（如最新迭代的GPT-4o、Claude 3.5或特定的开源微调模型）生成的文本，或是面对来自全新垂直领域（如高度专业化的医学报告或生僻编程语言代码）的文本时，监督模型的泛化能力往往呈现断崖式下跌 30。研究表明，通过引入一分类（One-class）算法与基于能量的学习方法，能够在一定程度上提升框架对多语言和未知模型攻击的抵抗力，但这依然无法从根本上消除训练数据偏差带来的隐患 28。

相比之下，以**Binoculars（双筒望远镜）算法**和Fast-DetectGPT为代表的零样本检测法，凭借其无需依赖特定模型训练数据的优势，正受到学术界的广泛关注 31。传统的单一困惑度检测器存在一个致命的逻辑漏洞：高度依赖输入提示词（Prompt Dependency）。如果用户通过提示词强制大语言模型创作极度生僻、风格怪异或包含大量专有名词的内容（例如“用莎士比亚风格描述量子力学”），输出文本的绝对困惑度会不可避免地飙升，从而被传统检测器误判为人类所写 34。

Binoculars算法通过巧妙的模型组合有效化解了这一难题。该算法并列引入两个紧密相关的预训练大语言模型（通常互为观察者模型和执行者模型），通过计算交叉困惑度（Cross-Perplexity）对文本的绝对困惑度进行数学归一化处理。其核心评分逻辑如下： ![][image5] 其中，交叉困惑度可以被视为任何大语言模型在面对该段文本时所能预期的“基线困惑度（Baseline Perplexity）”。通过这种相除的归一化操作，Binoculars算法成功剥离了由异常提示词带来的极端困惑度波动，将关注点重新聚焦于文本底层的机器生成特征。实验数据证实，在完全没有使用任何ChatGPT数据进行专项训练的前提下，Binoculars能够在控制假阳性率（FPR）低于0.01%的严苛条件下，实现对超过90%的各类型AIGC文本的精准检出，其鲁棒性大幅超越了此前的各种开源检测方案 30。

## **AIGC检测工具的性能基准测试与真实世界鲁棒性评估**

要构建有效的自动化降重与降AI策略，必须对当前主流AIGC检测工具的实际性能瓶颈与盲区有精确的量化认知。学术界近期的多个基准测试（Benchmarks）揭示了当前检测系统在面对现实世界复杂场景时的脆弱性。

### **真实场景基准测试（DetectRL与GEDE）的实证数据**

DetectRL是一个专门为评估AIGC检测器在真实世界复杂场景下可靠性而设计的最新基准测试。与以往仅使用理想化纯净文本的测试不同，DetectRL引入了多领域数据混入、人类后期修订、拼写对抗性噪声以及提示词攻击等变量 35。测试结果暴露出当前最先进（SOTA）检测器的严重局限性：

首先，在面对对抗性扰动攻击（Adversarial Perturbations，如字符替换、句子级拼写错误）时，零样本检测器（如DetectGPT）的性能遭遇重创，其平均接收者操作特征曲线下面积（AUROC）暴跌了39.28% 35。其次，不同大语言模型底层统计分布的差异也对检测器构成了巨大挑战，众多检测器在面对由Claude模型生成的长文本时普遍失效 35。在综合F1分数的评估中，基于鲁棒性优化的监督模型Rob-Base取得了93.02的最高平均F1得分，而备受推崇的Binoculars算法的平均F1得分仅为79.61，早期的DetectGPT更是低至29.05 35。此外，包含逾12,500篇LLM生成论文的GEDE（Generative Essay Detection in Education）数据集研究进一步证实，当前的检测器在处理“人类主导、AI润色（LLM-improved human-written texts）”这种中等贡献度级别的混合文本时，分类准确率最差，极易产生误判 36。

### **主流商业检测平台的准确率对标与特性分析**

在机构与高校实际部署的环境中，Turnitin、GPTZero、Copyleaks等商业闭源系统构成了查重与AI检测的主力防线。综合多家独立研究机构（如Kar et al., 2024 与 Lui et al., 2024）的实证评估，各平台的性能表现出了明显的分化 37。

| 商业检测系统 | 独立评测准确率 (主流基准) | 假阳性率 (FPR) 容忍度 | 核心技术优势与2025/2026迭代方向 |
| :---- | :---- | :---- | :---- |
| **Turnitin AI Detection** | 61% \- 94% 37 | 极低 (1-2%) 37 | 专为教育场景优化，极其重视降低假阳性率。2025年下半年算法更新后，引入了**AI绕过工具（AI Bypasser）识别能力**，并强制隐蔽低于20%置信度的评分以保护真实作者 38。对长篇未编辑的学术散文检测极准，但对深度混合编辑文本的召回率会显著下降 40。 |
| **GPTZero** | 93.5% \- 99% 41 | 极低 (\< 0.1%) 42 | 在提供高准确率的同时强调可解释性。最新版本通过强化学习训练模型识别对抗性提示词，在面对使用了伪装工具的对抗文本时，依然保持了93.5%的高召回率和零假阳性，确立了行业领先地位 42。 |
| **Copyleaks** | 64.8% \- 100% 37 | 低 41 | 在多项第三方独立测试中展现出极高的稳定性。其核心优势在于强大的多语言支持能力以及将传统抄袭比对与AIGC检测深度融合的架构，能够精准识别翻译抄袭及混合型合成文本 43。 |
| **Winston AI** | 67% \- 95% 37 | 中等 41 | 擅长句级维度的详细报告生成，同时涵盖AI检测与抄袭检查，但在处理极度复杂的对抗性学术文本时，其准确率波动较大 41。 |

### **假阳性危机：非母语偏见与“独立宣言”异常**

尽管检测系统的精度不断提升，假阳性（False Positives，即错将人类撰写的原创文本标记为AI生成）依然是整个行业悬而未决的致命危机。特别是当检测工具被用于高利害关系（High-Stakes）的学术不端指控时，算法的不透明性引发了严重的伦理争议 17。

这种假阳性并非随机错误，而是源于基于困惑度和突发性的检测算法所固有的系统性偏见（Systemic Bias）。斯坦福大学针对TOEFL论文的一项研究确凿地证明，AIGC检测器对非英语母语者（ESL/EFL）存在严重的歧视 21。由于非母语作者在写作时掌握的词汇量相对有限，且倾向于使用基础、规范的句法结构，其产出的文本在统计学上天然呈现出极低的困惑度与突发性。在检测算法的评估逻辑中，这种语言的熟练度不足被错误地等同于机器生成的机械性特征，导致非母语者面临远高于母语者的误判风险 21。

此外，检测算法的训练机制还导致了令人啼笑皆非的“历史文献异常”。例如，几乎所有的主流AI检测器都会将《美国独立宣言》或《圣经》的段落判定为100%由AI生成 21。这是因为这些著名的公共领域文本被海量地包含在各大语言模型（如GPT-4、Llama）的预训练语料库中。语言模型对这些文本的记忆达到了像素级的精准，因而在计算预测概率时，其困惑度趋近于绝对的零 21。在检测器看来，这便是最典型的机器生成特征。这一现象深刻揭示了，仅凭统计学特征进行判定，在面对模型训练集的记忆效应时是完全失效的。

## **针对AIGC检测的规避技术与高阶提示词工程**

检测系统的固有漏洞直接催生了不断进化的对抗性规避技术（Evasion Techniques）。为了在自动化降重工作流中成功降低文档的AI疑似度，仅仅依赖简单的同义词替换是无效的。必须深入剖析最前沿的对抗攻击模型，并将其逻辑转化为可执行的高阶提示词工程。

### **自动化对抗攻击模型的理论启示**

在计算机科学前沿研究中，学者们开发了多种自动化框架来系统性地击穿AIGC检测器，这些研究为降重策略提供了宝贵的理论支撑：

1. **策略优化与参数微调（StealthRL框架）**：StealthRL是一个基于强化学习的对抗性框架。它利用组相对策略优化（GRPO）算法和LoRA适配器对大语言模型进行微调，其优化的奖励函数旨在平衡“逃避检测”与“保持语义一致性”。实验表明，StealthRL不仅能将检测器的平均AUROC从0.74大幅压低至0.27，其攻击效果还能无缝转移到模型在训练期间从未见过的其他检测器上，这证明了当前所有的主流检测器在底层架构上共享着相同的脆弱统计学假设 48。  
2. **结构欺骗与视觉剥离（PDFuzz攻击）**：PDFuzz揭示了一种完全不改变文本语义的物理攻击方式。它利用PDF文档在视觉排版坐标与底层字符提取顺序之间的信息脱节，通过操纵字符的绝对定位，使得提取工具获取到的是完全混乱的字符序列，但在人类视觉阅读中却毫无异常。这种攻击瞬间将所有文本检测器的准确率降至随机猜测的水平（约50%） 49。尽管这种攻击在结构严密的DOCX文档中无法直接复现，但它启示我们在降重工作流中，文档解析的保真度对最终检测结果具有决定性影响。  
3. **基于重写的自适应对抗（AuthorMist）**：有别于固定距离的文本改写，AuthorMist通过机器学习自适应地学习原文与改写文本之间的距离函数，在保持高达0.94以上语义相似度的同时，实现了对各种SOTA检测器的完美逃避 50。

### **降重与降AIGC的高阶提示词工程范式**

在无法使用复杂强化学习微调的日常学术场景中，最稳定且符合伦理的降AIGC手段是采用精密的“提示词工程（Prompt Engineering）”。通过向大语言模型注入高度定制化的指令，强制其偏离预训练的概率分布，主动在输出中注入人类特有的困惑度与突发性。综合多项实证研究与绕过测试，有效降低AI得分的提示词策略可归纳为以下四个核心维度 51：

#### **1\. 人设降维与视角锚定（Persona and Perspective Anchoring）**

大语言模型在默认状态下，总是以一种全知全能、极度客观且毫无感情色彩的“机器上帝”视角进行输出。这种四平八稳的官腔是触发高AI得分的根源。

* **工程策略**：在提示词中必须强制锚定一个具体的、具有鲜明时代和专业背景的微观视角。例如：“请以一名正在攻读免疫学博士学位、母语为非英语的青年研究员的视角，重新审视并改写以下段落。在改写中，请带入你在实验室经历多次失败后的严谨与些许疲惫感”53。通过强制模型模拟特定人群的词汇分布，其输出结果将大幅偏离通用大模型的平滑基线，显著提升文本的统计困惑度。

#### **2\. 结构突变与微观节奏控制（Structural Burstiness Injection）**

未受约束的LLM生成的文本通常表现出极低的标准差，其句子长度与句法嵌套模式高度趋同。

* **工程策略**：利用硬性约束指令打破机器生成的机械节奏，强制进行微观层面的句法解构。例如指令应明确规定：“请改写以下内容，必须在段落中制造强烈的长短句交替节奏（Burstiness）：强制要求包含5-8字的极简短句、15-20字的过渡句，以及25-30字带有复杂从句的长句，并且这三种句式必须不规则地交替出现。严禁连续使用三个长度相似的句子” 53。这种人为干预的“爆发与停顿”，完美契合了检测算法对人类写作特征的统计画像。

#### **3\. 智力犹豫与批判性思维注入（Intellectual Hesitation and Nuance）**

为了追求逻辑闭环，机器生成的文本往往表现出绝对的确定性，缺乏人类学者在探讨前沿未知领域时的审慎与自我怀疑。

* **工程策略**：在提示词中要求模型在特定关键节点插入主观的限定与反思。例如：“在陈述该研究结论时，请表现出人类学者的‘智力犹豫（Intellectual Hesitation）’。请在段落中自然地插入1-2处主观限定语或轻微的让步（如‘尽管这一现象似乎表明’、‘目前尚不能基于此完全断定’、‘这在某种程度上可能被解释为’），并对所引用的方法论提出适度的、有根据的质疑” 51。这种策略在丰富句法树深度的同时，极大地削弱了机器生成的机械感。

#### **4\. 机械性过渡词的定向剥离（Transition Word Cleansing）**

诸如“此外（Furthermore）”、“总而言之（In conclusion）”、“值得注意的是（It is important to note that）”、“在当今快节奏的世界中（In today's fast-paced world）”等高频过渡词，已经成为各大AI检测算法预设的高权重“雷区”特征 51。

* **工程策略**：在提示词中内置一份明确的屏蔽词表（Blocklist）。指令模型：“在重构段落逻辑时，绝对禁止使用‘此外’、‘总而言之’、‘值得注意的是’等模式化连接词。必须完全依靠句子之间内在的语义递进与指代关系来实现自然过渡，或者使用更具针对性的领域专业术语来承上启下” 51。切断这些已知的高频词汇链，能够直接绕过检测器的浅层特征匹配网络。

## **构建端到端的自动化格式无损AI降重工作流**

理论的突破最终需要落脚于工程的实现。面对一篇带有复杂排版、公式、图表引用与脚注的DOCX学术论文，我们无法依赖人工进行繁琐的复制粘贴与手动调整。结合底层DOM解析技术与高阶Agentic提示词工程，我们可以构建一套全自动化、端到端（End-to-End）的文档合规工作流。该系统能够无缝摄入带格式的论文，智能化地评估并靶向重写高风险片段，最终输出一份查重率与AI疑似度均达标，且原始排版分毫不差的终稿文档 13。

该自动化工作流可解构为以下四个紧密耦合的核心阶段：

### **阶段一：高保真文档摄入与多模态语义分块（High-Fidelity Ingestion & Semantic Chunking）**

在这个阶段，系统绝对不能将DOCX粗暴地转换为纯文本字符串。必须借助高级文档对象解析器（如Python生态下的docx2python或具备复杂表格感知能力的LlamaParse引擎），深入遍历文档的OpenXML底层节点 1。

系统需构建一个高维度的内存映射表（Mapping Graph），不仅提取纯文本，更要将每一段提取出的纯文本与其在底层XML树中的精确位置（如特定的\<w:p\>和\<w:r\>标签索引）、所携带的格式属性集（\<w:rPr\>）、以及关联的列表层级元数据进行严格绑定 60。例如，包含Zotero或Mendeley引文域代码的句子，其文本在DOM树中会被拆分。系统通过语义分块（Chunking）将逻辑连贯的段落打包，赋予全局唯一的标识符（Chunk ID），为后续的靶向回注提供精确的坐标锚点。

### **阶段二：双流并发检测与局部红箱隔离（Dual-Stream Detection and Isolation）**

完成分块后，系统将映射表中的纯文本片段并发推送至两个独立的分析引擎进行评估：

1. **传统查重流（Similarity Checking API）**：对接如Turnitin Similarity或Copyleaks的查重接口，比对底层数据库，识别出因引用不当或过度借鉴导致的长字符串匹配抄袭。  
2. **AIGC检测流（AI-Detection API）**：对接GPTZero或Turnitin的AI检测接口，获取该分块在困惑度与突发性维度的综合AI置信度评分 15。

系统聚合双流报告，设定安全阈值（如：传统重复率 \> 10% 或 AI置信度 \> 20% 将触发警报）。超过阈值的文本块被标记为“红箱片段（Red-flagged Text）”并被隔离提取。未触发警报的安全文本块将被系统锁定，不进行任何修改，以绝对保障原文作者核心论点的原汁原味与语义的精准性。

### **阶段三：基于严格约束的Agentic智能改写（Constrained Agentic Rewriting）**

进入这一核心重构阶段，系统不再是进行简单的单轮API调用，而是启动一个多智能体协同机制（Agentic Workflow）进行迭代改写 63。 红箱文本被送入部署了前述“高阶提示词工程范式”的大语言模型节点（如配置了特定系统提示的Claude 3.5 Sonnet或GPT-4o）65。更为关键的是，在此步骤中必须向大模型施加强制性的**内容保真约束（Fidelity Constraints）**。系统指令会明确规定：“你必须在提升突发性并降低AI痕迹的同时，绝对保留原文中的所有参考文献括号标记（如 (Doe et al., 2024)）、特定的专业术语黑话、数学变量以及缩略词。任何对这些指定元素的破坏都将导致该轮改写失败。”12

改写生成的新文本并不会立即进入下一阶段，而是先由内部的质量控制验证器（QC Evaluator）进行快速校验：检查字符长度的漂移幅度（Length Inflation）是否在允许范围内、保留实体是否完整、并再次调用轻量级的开源检测器（如Binoculars本地部署版）进行二审测试 12。若验证失败，系统将动态调整提示词参数（如调高Temperature值或改变角色设定）触发重新生成，直至文本各项合规指标达标。

### **阶段四：格式感知重组与XML修补封装（Format-Aware Reintegration & XML Patching）**

这是保障文档完整性的终极步骤。系统取回经过检验的干净文本，利用阶段一构建的映射表，将新文本精准注回原DOCX文档的XML结构树中。

面对不可避免的文本长度变化与结构重组，系统采用Diff-Patch算法机制对节点进行显微手术式处理。如果原红箱片段的文本跨越了多个包含不同格式属性的运行块（Runs），系统会对比新旧文本的语义边界。为了最大程度继承格式，算法通常选择保留段落内第一个关键运行块的\<w:rPr\>格式节点，将降重后的完整纯文本注入该节点的\<w:t\>标签下，并静默清空该段落内剩余被替换运行块的文本值，而不删除其节点本身 8。

对于表格内的文本重写，系统直接通过OpenXML接口定位对应的\<w:tc\>单元格节点进行安全的文本节点替换，完全不触碰表格边框、合并属性或背景色等结构代码 9。经过这一系列精密的计算与替换，系统最终将内存中的DOM树重新打包、压缩并输出为新的DOCX文件。最终交付的文档不仅在查重与AIGC检测平台上无懈可击，更完美保留了多级标题、复杂公式排版、跨页大型表格以及由文献管理软件自动生成的活动引用字段，实现了真正意义上的全自动工业级文档合规重构 1。

## **总结与未来技术展望**

从剖析DOCX文档底层的OpenXML架构，到解构困惑度与突发性的统计学边界，再到构建基于高阶提示词工程与DOM重构的自动化端到端工作流，本研究全面展示了应对当前学术与商业领域AIGC检测危机的技术全景。

当前的局势清晰地表明，针对AIGC内容的检测与反检测策略，已经彻底沦为一场类似于网络安全攻防的“猫鼠游戏（Arms Race）”50。一方面，诸如Turnitin与GPTZero等头部检测平台正不断整合多维度的统计特征与深度学习模型，试图封堵对抗性绕过工具的漏洞；另一方面，通过强化学习微调的自动化攻击框架（如StealthRL）以及精妙绝伦的结构欺骗技术（如PDFuzz），又在不断轻易地撕裂这些检测防线 48。此外，基于纯粹统计学特征（困惑度/突发性）的检测机制所固有的理论缺陷，导致了不可避免的高利害假阳性问题，使得非母语作者与特定文风的群体面临着极大的系统性偏见与不公 21。

长远来看，单纯依赖后置的被动式统计学侦测软件来围堵AI生成文本不仅在技术上已显疲态，在逻辑上也注定无法穷尽大模型日益精进的拟真能力。未来的文本治理技术或将不可逆转地向源头数字水印（Watermarking）技术倾斜。通过强制大语言模型在生成文本的概率采样阶段，隐蔽且不可察觉地嵌入高频的水印信号（如Google的SynthID技术），平台将能够通过确定性的解码算法实现近乎100%准确率且零假阳性的AIGC追踪，从而彻底终结当前的统计学猜疑链 68。

而在更深远的学术伦理与教育管理层面，技术博弈的无解也促使我们进行深刻反思。高等教育机构与学术出版界应当逐步摒弃单纯依赖检测软件进行惩罚性治理的路径，转向积极拥抱AI整合型教学与评估体系（AI-integrated Pedagogies）17。这要求我们重新定义学术原创性的边界：将利用大模型进行数据整理、逻辑梳理和语言润色视为现代研究的标准化辅助流程，同时建立透明、规范的AI使用披露机制。当技术已经能够完美解构并重组任何文本形式时，未来的评估焦点必将从“文本是谁写出的”，回归到对研究设计逻辑、创新思想火花以及科学实验过程实质性贡献的考察之上。这才是保障知识生产纯粹性，驾驭而非被生成式AI洪流吞噬的最终归宿。

#### **引用的著作**

1. Improving Table Parsing for Word (.docx) Documents \- LlamaIndex, 访问时间为 三月 28, 2026， [https://www.llamaindex.ai/blog/improving-table-parsing-for-word-docx-documents](https://www.llamaindex.ai/blog/improving-table-parsing-for-word-docx-documents)  
2. Reading and writing Microsoft Word docx files with Python | Virantha Namal Ekanayake, 访问时间为 三月 28, 2026， [https://virantha.com/2013/08/16/reading-and-writing-microsoft-word-docx-files-with-python/](https://virantha.com/2013/08/16/reading-and-writing-microsoft-word-docx-files-with-python/)  
3. combine word document using python docx \- Stack Overflow, 访问时间为 三月 28, 2026， [https://stackoverflow.com/questions/24872527/combine-word-document-using-python-docx](https://stackoverflow.com/questions/24872527/combine-word-document-using-python-docx)  
4. How to parse and preserve text formatting (Python-Docx)? \- Stack Overflow, 访问时间为 三月 28, 2026， [https://stackoverflow.com/questions/69124345/how-to-parse-and-preserve-text-formatting-python-docx](https://stackoverflow.com/questions/69124345/how-to-parse-and-preserve-text-formatting-python-docx)  
5. How to keep current style in when inserting via OpenXML SDK? \- Stack Overflow, 访问时间为 三月 28, 2026， [https://stackoverflow.com/questions/5483480/how-to-keep-current-style-in-when-inserting-via-openxml-sdk](https://stackoverflow.com/questions/5483480/how-to-keep-current-style-in-when-inserting-via-openxml-sdk)  
6. Use OpenXML to replace text in DOCX file \- strange content \- Stack Overflow, 访问时间为 三月 28, 2026， [https://stackoverflow.com/questions/34002797/use-openxml-to-replace-text-in-docx-file-strange-content](https://stackoverflow.com/questions/34002797/use-openxml-to-replace-text-in-docx-file-strange-content)  
7. Python docx Replace string in paragraph while keeping style \- Stack Overflow, 访问时间为 三月 28, 2026， [https://stackoverflow.com/questions/34779724/python-docx-replace-string-in-paragraph-while-keeping-style](https://stackoverflow.com/questions/34779724/python-docx-replace-string-in-paragraph-while-keeping-style)  
8. python-docx-replace \- PyPI, 访问时间为 三月 28, 2026， [https://pypi.org/project/python-docx-replace/](https://pypi.org/project/python-docx-replace/)  
9. How to replace an Paragraph's text using OpenXML Sdk \- Stack Overflow, 访问时间为 三月 28, 2026， [https://stackoverflow.com/questions/4276077/how-to-replace-an-paragraphs-text-using-openxml-sdk](https://stackoverflow.com/questions/4276077/how-to-replace-an-paragraphs-text-using-openxml-sdk)  
10. How to keep style on open xml documents \- Stack Overflow, 访问时间为 三月 28, 2026， [https://stackoverflow.com/questions/29092858/how-to-keep-style-on-open-xml-documents](https://stackoverflow.com/questions/29092858/how-to-keep-style-on-open-xml-documents)  
11. How do I make a C\# program that can search and replace text in a word document while retaining the fortmatting : r/csharp \- Reddit, 访问时间为 三月 28, 2026， [https://www.reddit.com/r/csharp/comments/a4d20g/how\_do\_i\_make\_a\_c\_program\_that\_can\_search\_and/](https://www.reddit.com/r/csharp/comments/a4d20g/how_do_i_make_a_c_program_that_can_search_and/)  
12. Preserving document formatting during AI rewrites is way harder than the rewriting \- Reddit, 访问时间为 三月 28, 2026， [https://www.reddit.com/r/SaaS/comments/1pz66ue/preserving\_document\_formatting\_during\_ai\_rewrites/](https://www.reddit.com/r/SaaS/comments/1pz66ue/preserving_document_formatting_during_ai_rewrites/)  
13. How to Get AI to Edit Word Documents Without Breaking Formatting \- Vesence, 访问时间为 三月 28, 2026， [https://www.vesence.com/blog/ai-edit-word-documents](https://www.vesence.com/blog/ai-edit-word-documents)  
14. Cross sectional pilot study on clinical review generation using large language models \- PMC, 访问时间为 三月 28, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC11923074/](https://pmc.ncbi.nlm.nih.gov/articles/PMC11923074/)  
15. 维普论文检测【官方网站】-论文查重，毕业论文抄袭检测，24小时自助检测-VPCS.CQVIP.COM, 访问时间为 三月 28, 2026， [https://vpcs.fanyu.com/](https://vpcs.fanyu.com/)  
16. How Does an AI Detector Work? The Complete Guide, 访问时间为 三月 28, 2026， [https://gpt-watermark-remover.com/blog/how-ai-detectors-work](https://gpt-watermark-remover.com/blog/how-ai-detectors-work)  
17. Evaluating the Effectiveness and Ethical Implications of AI Detection Tools in Higher Education \- MDPI, 访问时间为 三月 28, 2026， [https://www.mdpi.com/2078-2489/16/10/905](https://www.mdpi.com/2078-2489/16/10/905)  
18. AI Content Detection Software Market Size & Share 2025-2032 \- Coherent Market Insights, 访问时间为 三月 28, 2026， [https://www.coherentmarketinsights.com/industry-reports/ai-content-detection-software-market](https://www.coherentmarketinsights.com/industry-reports/ai-content-detection-software-market)  
19. How Do AI Detectors Work? | Methods & Reliability \- Scribbr, 访问时间为 三月 28, 2026， [https://www.scribbr.com/ai-tools/how-do-ai-detectors-work/](https://www.scribbr.com/ai-tools/how-do-ai-detectors-work/)  
20. Detecting AI-Generated Code Assignments Using Perplexity of Large Language Models | Request PDF \- ResearchGate, 访问时间为 三月 28, 2026， [https://www.researchgate.net/publication/379285256\_Detecting\_AI-Generated\_Code\_Assignments\_Using\_Perplexity\_of\_Large\_Language\_Models](https://www.researchgate.net/publication/379285256_Detecting_AI-Generated_Code_Assignments_Using_Perplexity_of_Large_Language_Models)  
21. Why Perplexity and Burstiness Fail to Detect AI | Pangram Labs, 访问时间为 三月 28, 2026， [https://www.pangram.com/blog/why-perplexity-and-burstiness-fail-to-detect-ai](https://www.pangram.com/blog/why-perplexity-and-burstiness-fail-to-detect-ai)  
22. Perplexity and Burstiness in Writing \- Originality.ai, 访问时间为 三月 28, 2026， [https://originality.ai/blog/perplexity-and-burstiness-in-writing](https://originality.ai/blog/perplexity-and-burstiness-in-writing)  
23. Perplexity and Burstiness in AI and Human Writing: Two Important Concepts, 访问时间为 三月 28, 2026， [https://www.unic.ac.cy/ai-lc/2023/04/11/perplexity-and-burstiness-in-ai-and-human-writing-two-important-concepts/](https://www.unic.ac.cy/ai-lc/2023/04/11/perplexity-and-burstiness-in-ai-and-human-writing-two-important-concepts/)  
24. Spotting LLMs With Binoculars: Zero-Shot Detection of Machine-Generated Text \- arXiv, 访问时间为 三月 28, 2026， [https://arxiv.org/html/2401.12070v3](https://arxiv.org/html/2401.12070v3)  
25. Burstiness & Perplexity | Definition & Examples \- QuillBot, 访问时间为 三月 28, 2026， [https://quillbot.com/blog/ai-writing-tools/burstiness-and-perplexity/](https://quillbot.com/blog/ai-writing-tools/burstiness-and-perplexity/)  
26. How to Write Content Using ChatGPT that Outsmarts AI Detection Tools with 99% Accuracy, 访问时间为 三月 28, 2026， [https://www.reddit.com/r/ArtificialInteligence/comments/14bhhb7/how\_to\_write\_content\_using\_chatgpt\_that\_outsmarts/](https://www.reddit.com/r/ArtificialInteligence/comments/14bhhb7/how_to_write_content_using_chatgpt_that_outsmarts/)  
27. GPTZero Performance in Identifying Artificial Intelligence-Generated Medical Texts: A Preliminary Study \- PMC, 访问时间为 三月 28, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC10519776/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10519776/)  
28. Human Texts Are Outliers: Detecting LLM-generated Texts via Out-of-distribution Detection, 访问时间为 三月 28, 2026， [https://arxiv.org/html/2510.08602v1](https://arxiv.org/html/2510.08602v1)  
29. Detecting LLM-Generated Text with Performance Guarantees \- arXiv, 访问时间为 三月 28, 2026， [https://arxiv.org/html/2601.06586v1](https://arxiv.org/html/2601.06586v1)  
30. Spotting LLMs With Binoculars: Zero-Shot Detection of Machine-Generated Text \- arXiv, 访问时间为 三月 28, 2026， [https://arxiv.org/abs/2401.12070](https://arxiv.org/abs/2401.12070)  
31. Spotting LLMs With Binoculars: Zero-Shot Detection of Machine-Generated Text, 访问时间为 三月 28, 2026， [https://openreview.net/forum?id=iARAKITHTH](https://openreview.net/forum?id=iARAKITHTH)  
32. Spotting LLMs With Binoculars: Zero-Shot Detection of Machine-Generated Text \- GitHub, 访问时间为 三月 28, 2026， [https://raw.githubusercontent.com/mlresearch/v235/main/assets/hans24a/hans24a.pdf](https://raw.githubusercontent.com/mlresearch/v235/main/assets/hans24a/hans24a.pdf)  
33. Detecting LLM-Generated Text with Binoculars \- Hugging Face, 访问时间为 三月 28, 2026， [https://huggingface.co/blog/dmicz/binoculars-text-detection](https://huggingface.co/blog/dmicz/binoculars-text-detection)  
34. Zero-shot LLM text detectors in practice | by Vlad \- Medium, 访问时间为 三月 28, 2026， [https://medium.com/@vzzz/zero-shot-llm-text-detectors-in-practice-2b737ffcadd2](https://medium.com/@vzzz/zero-shot-llm-text-detectors-in-practice-2b737ffcadd2)  
35. DetectRL: Benchmarking LLM-Generated Text Detection in Real-World Scenarios \- arXiv, 访问时间为 三月 28, 2026， [https://arxiv.org/abs/2410.23746](https://arxiv.org/abs/2410.23746)  
36. \[2508.08096\] Assessing LLM Text Detection in Educational Contexts: Does Human Contribution Affect Detection? \- arXiv, 访问时间为 三月 28, 2026， [https://arxiv.org/abs/2508.08096](https://arxiv.org/abs/2508.08096)  
37. AI Detection and assessment \- an update for 2025 \- Artificial intelligence, 访问时间为 三月 28, 2026， [https://nationalcentreforai.jiscinvolve.org/wp/2025/06/24/ai-detection-assessment-2025/](https://nationalcentreforai.jiscinvolve.org/wp/2025/06/24/ai-detection-assessment-2025/)  
38. AI writing detection model \- Turnitin Guides, 访问时间为 三月 28, 2026， [https://guides.turnitin.com/hc/en-us/articles/28294949544717-AI-writing-detection-model](https://guides.turnitin.com/hc/en-us/articles/28294949544717-AI-writing-detection-model)  
39. Using the AI Writing Report \- Turnitin Guides, 访问时间为 三月 28, 2026， [https://guides.turnitin.com/hc/en-us/articles/22774058814093-Using-the-AI-Writing-Report](https://guides.turnitin.com/hc/en-us/articles/22774058814093-Using-the-AI-Writing-Report)  
40. The Truth About Turnitin's AI Detection Accuracy in 2025, 访问时间为 三月 28, 2026， [https://turnitin.app/blog/The-Truth-About-Turnitins-AI-Detection-Accuracy-in-2025.html](https://turnitin.app/blog/The-Truth-About-Turnitins-AI-Detection-Accuracy-in-2025.html)  
41. 9 Best AI Detectors With The Highest Accuracy in 2026 \- GPTZero, 访问时间为 三月 28, 2026， [https://gptzero.me/news/best-ai-detectors/](https://gptzero.me/news/best-ai-detectors/)  
42. GPTZero AI Detection Benchmarking: The Industry Standard in Accuracy, Transparency and Fairness, 访问时间为 三月 28, 2026， [https://gptzero.me/news/gptzero-ai-detection-benchmarking-the-industry-standard-in-accuracy-transparency-and-fairness/](https://gptzero.me/news/gptzero-ai-detection-benchmarking-the-industry-standard-in-accuracy-transparency-and-fairness/)  
43. Copyleaks AI Detector Most Accurate by 3rd-Party Studies, 访问时间为 三月 28, 2026， [https://copyleaks.com/blog/ai-detector-continues-top-accuracy-third-party](https://copyleaks.com/blog/ai-detector-continues-top-accuracy-third-party)  
44. Copyleaks vs. GPTZero: Which AI Detector Is More Accurate?, 访问时间为 三月 28, 2026， [https://copyleaks.com/blog/copyleaks-vs-gptzero](https://copyleaks.com/blog/copyleaks-vs-gptzero)  
45. Most Accurate AI Checker Tools in 2025 for Writers, Students & Professionals, 访问时间为 三月 28, 2026， [https://community.hubspot.com/t5/HubSpot-Academy-Support/Most-Accurate-AI-Checker-Tools-in-2025-for-Writers-Students-amp/m-p/1230317](https://community.hubspot.com/t5/HubSpot-Academy-Support/Most-Accurate-AI-Checker-Tools-in-2025-for-Writers-Students-amp/m-p/1230317)  
46. Turnitin's AI detection tool falsely flagged my work, triggering an academic integrity investigation. No evidence required beyond the score. : r/slatestarcodex \- Reddit, 访问时间为 三月 28, 2026， [https://www.reddit.com/r/slatestarcodex/comments/1k3op60/turnitins\_ai\_detection\_tool\_falsely\_flagged\_my/](https://www.reddit.com/r/slatestarcodex/comments/1k3op60/turnitins_ai_detection_tool_falsely_flagged_my/)  
47. The Imperfection of AI Detection Tools \- HumTech \- UCLA, 访问时间为 三月 28, 2026， [https://humtech.ucla.edu/technology/the-imperfection-of-ai-detection-tools/](https://humtech.ucla.edu/technology/the-imperfection-of-ai-detection-tools/)  
48. \[2602.08934\] StealthRL: Reinforcement Learning Paraphrase Attacks for Multi-Detector Evasion of AI-Text Detectors \- arXiv, 访问时间为 三月 28, 2026， [https://arxiv.org/abs/2602.08934](https://arxiv.org/abs/2602.08934)  
49. \[2508.01887\] Complete Evasion, Zero Modification: PDF Attacks on AI Text Detection \- arXiv, 访问时间为 三月 28, 2026， [https://arxiv.org/abs/2508.01887](https://arxiv.org/abs/2508.01887)  
50. \[2503.08716\] AuthorMist: Evading AI Text Detectors with Reinforcement Learning \- arXiv, 访问时间为 三月 28, 2026， [https://arxiv.org/abs/2503.08716](https://arxiv.org/abs/2503.08716)  
51. How to avoid plagiarism and AI detection in essays, research, or review papers in Turnitin, 访问时间为 三月 28, 2026， [https://www.youtube.com/watch?v=KYNs3vQjGos](https://www.youtube.com/watch?v=KYNs3vQjGos)  
52. Top 7 Proven Tips To Avoid AI Detection In Writing In 2025 \- GPTinf, 访问时间为 三月 28, 2026， [https://www.gptinf.com/blog/top-7-proven-tips-to-avoid-ai-detection-in-writing-in-2025](https://www.gptinf.com/blog/top-7-proven-tips-to-avoid-ai-detection-in-writing-in-2025)  
53. 降AI率效果最佳的6个提示词，基于2026年2月降AI效果综合测评！ \- 河北, 访问时间为 三月 28, 2026， [https://hebei.ifeng.com/c/8qbH5H1E0cw](https://hebei.ifeng.com/c/8qbH5H1E0cw)  
54. 15+ Best Prompts to Humanize AI Text (And the Tool That Does It Better) \- Lynote Blog, 访问时间为 三月 28, 2026， [https://lynote.ai/blog/best-prompts-to-humanize-ai-text](https://lynote.ai/blog/best-prompts-to-humanize-ai-text)  
55. What is the best prompt you've used or created to Humanize AI Text? \- Reddit, 访问时间为 三月 28, 2026， [https://www.reddit.com/r/ChatGPTPro/comments/1jv183x/what\_is\_the\_best\_prompt\_youve\_used\_or\_created\_to/](https://www.reddit.com/r/ChatGPTPro/comments/1jv183x/what_is_the_best_prompt_youve_used_or_created_to/)  
56. Can everyone share their favorite tips on how to best bypass AI-detection websites like quillbot and zerogpt? \- Reddit, 访问时间为 三月 28, 2026， [https://www.reddit.com/r/ChatGPTPromptGenius/comments/1m7cxo6/can\_everyone\_share\_their\_favorite\_tips\_on\_how\_to/](https://www.reddit.com/r/ChatGPTPromptGenius/comments/1m7cxo6/can_everyone_share_their_favorite_tips_on_how_to/)  
57. 访问时间为 三月 28, 2026， [https://intellectualead.com/perplexity-burstiness-guide/\#:\~:text=Diversify%20AI%20Writing%20Structure%20(Sentence,sentences%20with%20long%2C%20complex%20ones.](https://intellectualead.com/perplexity-burstiness-guide/#:~:text=Diversify%20AI%20Writing%20Structure%20\(Sentence,sentences%20with%20long%2C%20complex%20ones.)  
58. I Tried Bypassing Turnitin's New AI Detection for 30 Days Here's What I found \- YouTube, 访问时间为 三月 28, 2026， [https://www.youtube.com/watch?v=6oTmC5DRHvw](https://www.youtube.com/watch?v=6oTmC5DRHvw)  
59. (PDF) AI-Driven end-to-end workflow optimization and automation system for SMEs, 访问时间为 三月 28, 2026， [https://www.researchgate.net/publication/385648813\_AI-Driven\_end-to-end\_workflow\_optimization\_and\_automation\_system\_for\_SMEs](https://www.researchgate.net/publication/385648813_AI-Driven_end-to-end_workflow_optimization_and_automation_system_for_SMEs)  
60. docx2python \- PyPI, 访问时间为 三月 28, 2026， [https://pypi.org/project/docx2python/](https://pypi.org/project/docx2python/)  
61. LiteParse: Local Document Parsing for AI Agents \- LlamaIndex, 访问时间为 三月 28, 2026， [https://www.llamaindex.ai/blog/liteparse-local-document-parsing-for-ai-agents](https://www.llamaindex.ai/blog/liteparse-local-document-parsing-for-ai-agents)  
62. Technical Comparison — Python Libraries for Document Parsing | by chenna \- Medium, 访问时间为 三月 28, 2026， [https://medium.com/@hchenna/technical-comparison-python-libraries-for-document-parsing-318d2c89c44e](https://medium.com/@hchenna/technical-comparison-python-libraries-for-document-parsing-318d2c89c44e)  
63. End-to-End Agentic Workflow: Campaign Creation to Localized Video \- YouTube, 访问时间为 三月 28, 2026， [https://www.youtube.com/watch?v=f7aWmxQ7l0w](https://www.youtube.com/watch?v=f7aWmxQ7l0w)  
64. Transforming End-to-End Testing with Generative Agentic Workflows \- Medium, 访问时间为 三月 28, 2026， [https://medium.com/transforming-testing-with-generative-ai/transforming-end-to-end-testing-with-generative-agentic-workflows-c29f4aae6a0a](https://medium.com/transforming-testing-with-generative-ai/transforming-end-to-end-testing-with-generative-agentic-workflows-c29f4aae6a0a)  
65. Claude AI and DOCX Reading: formats, accuracy, and workflows for document interpretation in 2025 \- Data Studios, 访问时间为 三月 28, 2026， [https://www.datastudios.org/post/claude-ai-and-docx-reading-formats-accuracy-and-workflows-for-document-interpretation-in-2025](https://www.datastudios.org/post/claude-ai-and-docx-reading-formats-accuracy-and-workflows-for-document-interpretation-in-2025)  
66. Can any AI humanizer handle academic citations without messing them up? \- Reddit, 访问时间为 三月 28, 2026， [https://www.reddit.com/r/edtech/comments/1mv9xvg/can\_any\_ai\_humanizer\_handle\_academic\_citations/](https://www.reddit.com/r/edtech/comments/1mv9xvg/can_any_ai_humanizer_handle_academic_citations/)  
67. Replacing cell text and keeping existing style and alignment · Issue \#194 · python-openxml/python-docx \- GitHub, 访问时间为 三月 28, 2026， [https://github.com/python-openxml/python-docx/issues/194](https://github.com/python-openxml/python-docx/issues/194)  
68. Enhancing the Robustness of AI-Generated Text Detectors: A Survey \- MDPI, 访问时间为 三月 28, 2026， [https://www.mdpi.com/2227-7390/13/13/2145](https://www.mdpi.com/2227-7390/13/13/2145)  
69. Distinguishing Reality from AI: Approaches for Detecting Synthetic Content \- MDPI, 访问时间为 三月 28, 2026， [https://www.mdpi.com/2073-431X/14/1/1](https://www.mdpi.com/2073-431X/14/1/1)

[image1]: <data:image/png;base64,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>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA0AAAAaCAYAAABsONZfAAAApUlEQVR4XmNgGAUDDAKAeC4Qz0LDM4FYGEkdVjAJiP8DMSO6BC7AC8SHGSCaiAaaQPwWiL+iS+ADQQwQW06jS+ADMP/MQZfABWBO+wTE+mhyOAGy0wTR5EAAJIYRooScBhJnQRYAmQKyAaQpGlkCCkA2+KELIge1MZocCIDExNEF1zJAbFnKgHC3NBAnA/FHIP4HFQMDSyD+yQDRgA+TFG+jABcAAL9QKLsWBxQFAAAAAElFTkSuQmCC>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFAAAAAZCAYAAACmRqkJAAAD8ElEQVR4Xu2YS6hOURTHl7xD3q+QR0oilFdkRJQ8kyJkYsCADIQIk5uhRxISGcnEQHmGuEUmJpRHkUIeRShFSR7r1z6L/S37HN9377ncwfevf/eevc7ZZ+//Xq/zidRRRx111FFHK0LXjGWimx/4R2ij7Kls6w15GK08pDyqfJ7xTHYNDyjnKNvbAxEmKR8pp3pDM8FhsIb/BURsUHb3hhT6KBcrtyq/K3cpl2Zco7yu/KG8bQ9EuCrhRbywTPxvAUFv5RapYW9zlU+Vg9w4ExyUIGI7Z8Nbh7uxMtAaBAQflRP9YB52K88rO3mDBO9EwIHRWH8JwlZ9QjWgtQj4UKrc4wjla+UMb5DgkU8lCGgT8feEcnB2nQfCIH65v85DkYAccD/5neT9dZlYImHfC73Bgxu4Ea+KwWbJA9goFgaqFDmxSzQWY5iE3PlG+VhCkdmRXV+QvyfnPAFPKl8qXynfKVdn/8M70X1lgfD9JCE6C8ENqRy3TflNeUsqvc08NoWhypvK6RJakRsSitMR5UUJ71nw6+40UgIi+jIJhwoR84qyr/KwhHnLBinrmYR35UYOi22UsABrY+B7CULMkz/Dw07Gg5fsVa7Krk1A7rVnviinZXYwTrlBKtuklIDrpDKFsCkixzbZFAGZZ6VyljdkoEO5L0Gf3D6XPpBwwEuqRZ6AhPR6CbkOmKcS7oQ9OXZkZjMcU16WygV6ATlAWiqDpRDmR4TxGWsFKYsUs8kbMphzwVwB2QCnd9obCpAnoAdNOHOTjGuBF9BjrdTmcRzAIuVySX8Q5MEiqFFyBLSTZDEsqloUCciLrCoyN96NlwPyGOHdMbs+q3wQ2Q0pAam2bJ48zWHHEcP4iujawDiiUbgQ0NuuSZirs7MZLD3wwZAsmCbEZ+VkZyuCTeyLzhjlW6nMeZygfddSBPhs5LnhEgrOEwlNfAwvIAdyT0LxsbbqRWSnynvB2fA5CcXM53DAlxY5lBD23YfBUhBRmsRmCd5HazDK2YrA4jgVPDgGG2S+u8ohErwkFpBnWBSYIME7SNJ+A15AOwzyHMWEzsAEHCDBk62HZW3bJXhWbuWUkFZOSXGjzJxfpbborBpU0tTEnDYe0yO7JlQQyApLDLzYCkuvaNwLCNhk3Ijbe1LeBcwD8c48gUgxtEF0Aj6awHnlJckP8WaBSZs7ORsgJBuksrlOCdgUFOVAcir971jlRmczkL95vsXwQTnbD9YA+sz9En4Wi1GWgIZUFcYrjyv3SfrLCLtvr0oHn3mNkl5ANWBxqR8vyhbQQDjPj66Lfjjl3il+sCXAifLJFy+suUDUnX7wH6GDco9ypjfUURJ+Alc9vjAp1Pu7AAAAAElFTkSuQmCC>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAcAAAAaCAYAAAB7GkaWAAAAhUlEQVR4XmNgGNZAEIgZ0QVBQBiInwOxJroEDHCgCxAEzAwQYzGAChCfBuLXQCyPLOECxP0MEBemA3EEsqQnEJsCMScQ7wBiRWRJGNAB4vcMOPzYAMT/0AVBgB+ITwDxdSBWBuJAZElfIP4PpZczoHlJhgGiaz8QmyBLwAAo2CTRBQcVAAASQQ9WYi6BuQAAAABJRU5ErkJggg==>

[image5]: <data:image/png;base64,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>