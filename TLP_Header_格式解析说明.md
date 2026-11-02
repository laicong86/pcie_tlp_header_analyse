# PCIe TLP Header 格式解析说明（Flit Mode / Non-Flit Mode）

> **来源**：PCI Express® Base Specification Revision 7.0（7.0-1.0-PUB），§2.2.1 Common Packet Header Fields
> **用途**：作为 TLP 解析工具（输入一段 TLP 字节流 → 输出结构化字段）的实现依据
> **文档约定**：位号写作 `[7:0]`，字节内 bit7 为最高位（规范图示左侧为 bit7）；`DW` = 32 bit；`R` = Reserved（发送方置 0，接收方忽略）

---

## 0. 为什么两种模式必须分开处理

PCIe 7.0 同时定义了两套 TLP 头格式：

| 维度 | Non-Flit Mode (NFM) | Flit Mode (FM) |
|---|---|---|
| 头长度来源 | `Fmt[2:0]` + `Type[4:0]` → 3 DW 或 4 DW | `Type[7:0]` → Header Base 1~7 DW，再叠加 OHC |
| Type 宽度 | 5 bit（bit4:0） | 8 bit（整个 byte 0） |
| 可选扩展头 | End-End TLP Prefix（独立 1 DW 单元） | OHC（A/B/C/E，紧跟 Header Base） |
| 尾部 | `TD=1` → 1 DW ECRC | `TS[2:0]` → 0~5 DW Trailer（含 IDE MAC/PCRC） |
| TC/Attr/Length | 定义见 §2.2.1.1 | 定义与 NFM 完全相同（§2.2.1.2 明确复用） |

> 关键结论：**FC 与 TC/Attr/Length 语义两模式一致**，差异集中在 `Type` 解码、头长度计算、以及"扩展内容放哪儿"（Prefix vs OHC）。

---

## 1. TLP 总体结构

### 1.1 Non-Flit Mode

```
┌──────────────┬──────────────────┬──────────────┬──────────────────┐
│ Local Prefix │  TLP Header      │ Data Payload │ Trailer (ECRC)   │
│ 0..n × 1DW   │ 3 DW 或 4 DW     │ 0..1024 DW   │ 0 或 1 DW (TD=1) │
│ (Fmt=100)    │                  │              │                  │
└──────────────┴──────────────────┴──────────────┴──────────────────┘
   ↑ 可多个、连续      ↑ 主体                ↑ Length 决定      ↑ TD 位决定
```

TLP Grammar（§2.2.1.1，Figure 2-3）：

```
TLP = {TLP Prefix}  TLP Header  [Data Payload]  [TLP Digest]
```

### 1.2 Flit Mode

TLP Grammar（§2.2.1.2 原文列举）：

- zero or more 1 DW Local TLP Prefixes
- **TLP Header Base**，长度由 `Type[7:0]` 决定，其后跟 **0~7 DW 的 OHC**（由 `OHC[4:0]` 指示）
- TLP data payload of 0 to 1024 DW
- **TLP Trailer**，是否存在由 `TS[2:0]` 决定

```
┌──────────────┬──────────────────┬──────────────────┬──────────────┬───────────────┐
│ Local Prefix │  Header Base     │  OHC             │ Data Payload │ Trailer       │
│ 0..n × 1DW   │ 1..7 DW          │ 0..7 DW          │ 0..1024 DW   │ 0..5 DW       │
│              │ (Type[7:0])      │ A-B-C-E 顺序     │              │ (TS[2:0])     │
└──────────────┴──────────────────┴──────────────────┴──────────────┴───────────────┘
```

> 注意：`Header Base + OHC` 才是"完整的 TLP Header"；Trailer **不属于**头部，但在字节流中紧跟在 payload 之后。

---

## 2. Non-Flit Mode 通用包头（§2.2.1.1）

### 2.1 所有 TLP（含前缀）都有的字段（Figure 2-4）

| 字节 | 位 | 字段 | 说明 |
|---|---|---|---|
| byte 0 | [7:5] | `Fmt[2:0]` | TLP 格式 |
| byte 0 | [4:0] | `Type[4:0]` | TLP 类型 |

> 目的：`Fmt` + `Type` 足以判定"头部剩余部分有多长"以及"是否带数据载荷"。

### 2.2 通用头 4 字节完整位图（Figure 2-5, Page 158）

**Fields Present in All Non-Flit Mode TLP Headers**

| 字节 | bit7 | bit6 | bit5 | bit4 | bit3 | bit2 | bit1 | bit0 |
|---|---|---|---|---|---|---|---|---|
| **+0** | `Fmt[2]` | `Fmt[1]` | `Fmt[0]` | `Type[4]` | `Type[3]` | `Type[2]` | `Type[1]` | `Type[0]` |
| **+1** | `T9` (Tag[9]) | `TC[2]` | `TC[1]` | `TC[0]` | `T8` (Tag[8]) | `A2` (Attr[2]) | `R` | `TH` |
| **+2** | `TD` | `EP` | `Attr[1]` | `Attr[0]` | `AT[1]` | `AT[0]` | `Length[9]` | `Length[8]` |
| **+3** | `Length[7]` | `Length[6]` | `Length[5]` | `Length[4]` | `Length[3]` | `Length[2]` | `Length[1]` | `Length[0]` |

> 规范图 Figure 2-5 的呈现方式为：`+0` 字节 = `Fmt | Type`；`+1` = `T9 | TC | T8 | A2 | R | TH`；`+2` = `TD | EP | Attr[1:0] | AT | Length[1:0]`；`+3` = `Length[7:0]`。上表即其逐位展开，可直接用于代码映射。

### 2.3 字段语义

| 字段 | 位置 | 宽度 | 语义 |
|---|---|---|---|
| `Fmt[2:0]` | byte0[7:5] | 3 | 头长 + 有无数据；`100b` 表示这是 TLP Prefix |
| `Type[4:0]` | byte0[4:0] | 5 | TLP 类型，同时决定 Switch 路由方式 |
| `TC[2:0]` | byte1[6:4] | 3 | Traffic Class（§2.2.6.6） |
| `T8` / `T9` | byte1[3] / byte1[7] | 1 / 1 | 10-bit Tag 的 `Tag[8]` / `Tag[9]`。NFM 中 Tag 高位不连续放置；不支持 10-bit Tag 的 Requester 必须置 0 |
| `A2` | byte1[2] | 1 | `Attr[2]`，与 byte2 的 `Attr[1:0]` 组成 3 bit 属性 |
| `R` | byte1[1] | 1 | Reserved。历史上是 Lightweight Notification 的 LN 位，已废弃；接收方忽略 |
| `TH` | byte1[0] | 1 | TLP Hints：1 = 头部带 TPH 内容（可能含 TPH Prefix） |
| `TD` | byte2[7] | 1 | TLP Digest：1 = TLP 末尾有 1 DW ECRC |
| `EP` | byte2[6] | 1 | Error Poisoned：1 = 该 TLP 已投毒 |
| `Attr[1:0]` | byte2[5:4] | 2 | Attributes（与 A2 合成 `Attr[2:0]`，§2.2.6.3） |
| `AT[1:0]` | byte2[3:2] | 2 | Address Type：`00b` 未翻译 / `01b` Translation Request / `10b` 已翻译 / `11b` 保留（Table 10-1）。仅对 Memory Request（及 FM 的 Address Routed Message）定义，其余类型 Reserved |
| `Length[9:0]` | byte2[1:0] + byte3[7:0] | 10 | 数据载荷（或所引用数据）长度，单位 DW |

**Length 编码（Table 2-4）**：

| Length[9:0] | 载荷大小 |
|---|---|
| `00 0000 0001b` ~ `11 1111 1111b` | 1 DW ~ 1023 DW |
| `00 0000 0000b` | **1024 DW**（编码回绕，最易写错的一点） |

约束：

- 数据必须 4 字节自然对齐，长度必须是 DW 的整数倍。
- 对不含数据/不引用数据的 TLP（`Cpl`、`CplLk`、大多数 Message）该字段 Reserved（例外见各类型定义）。

### 2.4 Fmt[2:0] 编码（Table 2-2）

| Fmt[2:0] | 含义 |
|---|---|
| `000b` | 3 DW header，无数据 |
| `001b` | 4 DW header，无数据 |
| `010b` | 3 DW header，带数据 |
| `011b` | 4 DW header，带数据 |
| `100b` | **TLP Prefix**（Type[4]=0 为 Local，=1 为 End-End） |
| 其余 | Reserved（Malformed） |

派生规则（解析器可直接用）：

```
header_dw  = (Fmt[2]==0) ? (3 + Fmt[0]) : PREFIX   // Fmt[2]=1 → 前缀
has_data   = (Fmt[2]==0) ? (Fmt[1]==1) : false
```
> 等价写法：`header_dw = 3 + (Fmt & 1)`，`has_data = (Fmt >> 1) & 1`（仅当 `Fmt < 4`）。

### 2.5 Fmt[2:0] + Type[4:0] 完整编码（Table 2-3）

| Name | Fmt[2:0] | Type[4:0] | 说明 |
|---|---|---|---|
| MRd | 000 / 001 | 0 0000 | Memory Read Request（32b / 64b） |
| MRdLk | 000 / 001 | 0 0001 | Memory Read Request-Locked |
| MWr | 010 / 011 | 0 0000 | Memory Write Request |
| IORd | 000 | 0 0010 | I/O Read Request |
| IOWr | 010 | 0 0010 | I/O Write Request |
| CfgRd0 | 000 | 0 0100 | Type 0 配置读 |
| CfgWr0 | 010 | 0 0100 | Type 0 配置写 |
| CfgRd1 | 000 | 0 0101 | Type 1 配置读 |
| CfgWr1 | 010 | 0 0101 | Type 1 配置写 |
| TCfgRd | 000 | 1 1011 | 已废弃（原 Trusted Config Read），接收方按 Malformed 处理 |
| DMWr | 010 / 011 | 1 1011 | Deferrable Memory Write（原 TCfgWr 编码） |
| Msg | 001 | 1 0 r2r1r0 | Message，无数据；`r[2:0]` = 路由方式（Table 2-20） |
| MsgD | 011 | 1 0 r2r1r0 | Message，带数据；`r[2:0]` = 路由方式 |
| Cpl | 000 | 0 1010 | Completion 无数据 |
| CplD | 010 | 0 1010 | Completion 带数据 |
| CplLk | 000 | 0 1011 | Locked Read 的完成（仅错误场景） |
| CplDLk | 010 | 0 1011 | Locked Read 的完成 |
| FetchAdd | 010 / 011 | 0 1100 | AtomicOp FetchAdd |
| Swap | 010 / 011 | 0 1101 | AtomicOp Swap |
| CAS | 010 / 011 | 0 1110 | AtomicOp CAS |
| LPrfx | 100 | 0 L3L2L1L0 | Local TLP Prefix（见 §2.7） |
| EPrfx | 100 | 1 E3E2E1E0 | End-End TLP Prefix（见 §2.7） |

> 说明：Fmt 同时给出两个值时，第一个对应 32-bit 地址，第二个对应 64-bit 地址。

### 2.6 NFM 头长度判定

```
if Fmt == 0b100:        # TLP Prefix，长度 1 DW，需要继续看下一个 Fmt
    dw = 1
else:
    dw = 3 + (Fmt & 1)  # 3 或 4
```

**Prefix 链规则**：

- 一个 TLP 可以有 **0 个或多个 Local Prefix**（紧跟 TLP 头之前，可与其他前缀交错），
- 一个 TLP 最多 **4 个 End-End Prefix**（超过 → Malformed TLP），
- 每个前缀恒为 1 DW，自身也用 `Fmt=100b` + `Type[4:0]` 标识类型，
- 扫描直到遇到 `Fmt != 100b` 的第一个 DW，即为 TLP Header 起点。

### 2.7 前缀类型编码

**Local TLP Prefix（Fmt=100b, Type[4]=0，Table 2-38）**

| L[3:0] | 名称 | 说明 |
|---|---|---|
| 0000 | MR-IOV | MR-IOV TLP Prefix |
| 1101 | FlitModePrefix | Flit Mode Local TLP Prefix（仅 FM 允许） |
| 1110 | VendPrefixL0 | 厂商自定义 Local Prefix 0 |
| 1111 | VendPrefixL1 | 厂商自定义 Local Prefix 1 |
| 其余 | Reserved | — |

**End-End TLP Prefix（Fmt=100b, Type[4]=1，Table 2-39）**

| E[3:0] | 名称 | 说明 |
|---|---|---|
| 0000 | TPH | TLP Processing Hints |
| 0001 | PASID | PASID Prefix |
| 0010 | IDE | 标记 IDE TLP |
| 1110 | VendPrefixE0 | 厂商自定义 End-End Prefix 0 |
| 1111 | VendPrefixE1 | 厂商自定义 End-End Prefix 1 |
| 其余 | Reserved | — |

---

## 3. Flit Mode 通用包头（§2.2.1.2）

### 3.1 Header Base 首 DW（Figure 2-6, Page 160）

所有 FM TLP 的 Header Base 首 DW 字段布局完全一致：

| 字节 | bit7 | bit6 | bit5 | bit4 | bit3 | bit2 | bit1 | bit0 |
|---|---|---|---|---|---|---|---|---|
| **+0** | Type[7] | Type[6] | Type[5] | Type[4] | Type[3] | Type[2] | Type[1] | Type[0] |
| **+1** | TC[2] | TC[1] | TC[0] | OHC[4] | OHC[3] | OHC[2] | OHC[1] | OHC[0] |
| **+2** | TS[2] | TS[1] | TS[0] | Attr[2] | Attr[1] | Attr[0] | Length[9] | Length[8] |
| **+3** | Length[7] | Length[6] | Length[5] | Length[4] | Length[3] | Length[2] | Length[1] | Length[0] |

> **与 NFM 的三处结构性差异**：
> 1. `Type` 扩到 8 bit，占满 byte0；
> 2. 原 `Fmt`、`T8/T9`、`A2`、`R`、`TH`、`TD`、`EP`、`AT` 全部消失 —— `Attr` 合并为 3 bit 连续字段，`AT`/`EP` 移到类型相关的头部位置（AT 在地址 DW 的 bit[1:0]），`TD` 由 `TS` 取代；
> 3. 新增 `OHC[4:0]`（可选头内容）与 `TS[2:0]`（尾部大小）。

### 3.2 字段语义

| 字段 | 位置 | 宽度 | 语义 |
|---|---|---|---|
| `Type[7:0]` | byte0[7:0] | 8 | 类型，必须被所有接收方完整解码；同时决定 Header Base 长度、是否带载荷、FC 类型（Table 2-5） |
| `TC[2:0]` | byte1[7:5] | 3 | 与 NFM 相同 |
| `OHC[4:0]` | byte1[4:0] | 5 | Orthogonal Header Content 存在指示（§3.3） |
| `TS[2:0]` | byte2[7:5] | 3 | Trailer Size（§3.6） |
| `Attr[2:0]` | byte2[4:2] | 3 | 与 NFM 的 `Attr[2:0]` 语义相同 |
| `Length[9:0]` | byte2[1:0]+byte3[7:0] | 10 | 与 NFM 相同（0 → 1024 DW） |

补充规则（§2.2.1.2）：

- NFM 的 byte1 bit1（原 LN 位）在 FM 为 Reserved，**必须为 0b**；NFM→FM 翻译时忽略，FM→NFM 时置 0。
- NOP TLP（Type = 0x00）除 Type 外所有头部字段 Reserved，接收方必须无副作用丢弃。
- 一个 Port 若收到超出其支持的 OHC 内容，可按规则丢弃未支持的 Header Base/OHC 部分（日志中不含），但 Switch 端口必须按规范缓存与转发。

### 3.3 OHC[4:0] 语义与排列

`OHC[4:0]` 不是长度字段，而是"哪些 OHC 存在"的位图：

| 位 | 编码 | 含义 | 占 DW |
|---|---|---|---|
| OHC[0] | `x xxx1b` | OHC-A 存在（具体为 A1~A5 由 TLP 类型决定） | 1 |
| OHC[1] | `x xx1xb` | OHC-B 存在 | 1 |
| OHC[2] | `x x1xxb` | OHC-C 存在 | 1 |
| OHC[4:3] | `0 0xxxb` | 无 OHC-E | 0 |
| | `0 1xxxb` | OHC-E1 | 1 |
| | `1 0xxxb` | OHC-E2 | 2 |
| | `1 1xxxb` | OHC-E4 | 4 |

规则：

- OHC 必须**紧跟 Header Base**，且按 **A → B → C → E** 的顺序排列（任意组合允许）；
- 部分 TLP 类型强制要求特定 OHC（缺失时 Request 按 Unsupported Request、Completion 按 Unexpected Completion 处理）；
- OHC 长度合计：`OHC_dw = OHC[0] + OHC[1] + OHC[2] + e_dw`，其中 `e_dw = {00:0, 01:1, 10:2, 11:4}[OHC[4:3]]`。

### 3.4 OHC-A 系列（1 DW，Figure 2-7 ~ 2-11）

**哪些 TLP 用哪个变体（Table 2-6）**

| 变体 | 适用 TLP | 关键内容 |
|---|---|---|
| OHC-A1 | 带显式 Byte Enables 的 Memory Request、带 PASID 的 Address Routed Message / 路由到 RC 的 Message、Translation Request | Byte Enables、PASID/PV、ER/PMR、NW |
| OHC-A2 | I/O Request | Byte Enables |
| OHC-A3 | Configuration Request | Destination Segment / DSV、Byte Enables |
| OHC-A4 | 需要 Destination Segment 和/或 PASID 的 ID-Routed Message | Destination Segment、PASID |
| OHC-A5 | 按 §2.2.9.2 要求携带的 Completion | Destination Segment、Completer Segment、Cpl. Status、Lower Address[1:0] |
| 其它 TLP 上的 OHC-A | — | 全部 bit Reserved |

**OHC-A1（Figure 2-7）**

| 字节 | 位 | 字段 |
|---|---|---|
| +0 | [7] | NW（No Write，仅 Translation Request 有意义） |
| +0 | [6] | PV（PASID Valid） |
| +0 | [5] | PMR（Privileged Mode Requested，仅 Translation/Page Request） |
| +0 | [4] | ER（Execute Requested，同上） |
| +0 | [3:0] + +1[7:0] + +2[7:0] | PASID[19:0]（PV=0 时 Reserved） |
| +3 | [7:4] | Last DW BE[3:0] |
| +3 | [3:0] | First DW BE[3:0] |

**OHC-A2（Figure 2-8）**：+0~+2 全 Reserved；+3[7:4] = Last DW BE，+3[3:0] = First DW BE。

**OHC-A3（Figure 2-9）**

| 字节 | 位 | 字段 |
|---|---|---|
| +0 | [7:0] | Destination Segment（DSV=0 时 Reserved） |
| +1 | [7:0] | R |
| +2 | [7] | DSV（Destination Segment Valid） |
| +2 | [6:0] | R |
| +3 | [7:4] / [3:0] | Last DW BE / First DW BE |

**OHC-A4（Figure 2-10）**

| 字节 | 位 | 字段 |
|---|---|---|
| +0 | [7:0] | Destination Segment（DSV=0 时 Reserved） |
| +1 | [7:0] | PASID[15:8] |
| +2 | [7] | DSV |
| +2 | [6] | PV |
| +2 | [5:4] | R |
| +2 | [3:0] | PASID[19:16] |
| +3 | [7:0] | PASID[7:0] |

**OHC-A5（Figure 2-11）**

| 字节 | 位 | 字段 |
|---|---|---|
| +0 | [7:0] | Destination Segment（DSV=0 时 Reserved） |
| +1 | [7:0] | Completer Segment |
| +2 | [7] | DSV |
| +2 | [6:0] | R |
| +3 | [7:4] | R |
| +3 | [3:2] | LA[1:0] = Lower Address[1:0] |
| +3 | [1:0] | Cpl. Status |

### 3.5 OHC-B（1 DW，Figure 2-12）

仅用于 Address Routed Request；出现在其它 TLP 上时全部 bit Reserved。

| 字节 | 位 | 字段 |
|---|---|---|
| +0 | [7:0] | R |
| +1 | [7:0] | ST[15:8]（Steering Tag 高字节） |
| +2 | [7:0] | ST[7:0] |
| +3 | [7:6] | PH[1:0]（Processing Hint） |
| +3 | [5:4] | HV[1:0]（Hints Valid） |
| +3 | [3:1] | AMA[2:0]（AV=0 时 Reserved） |
| +3 | [0] | AV（AMA Valid） |

HV 编码：

| HV | 有效范围 |
|---|---|
| `00b` | PH、ST[15:0] 均无效（Reserved） |
| `01b` | PH、ST[7:0] 有效；ST[15:8] 无效 |
| `10b` | Reserved 编码，接收方按 `00b` 处理 |
| `11b` | PH、ST[15:0] 均有效 |

### 3.6 OHC-C（1 DW，Figure 2-13）

| 字节 | 位 | 字段 |
|---|---|---|
| +0 | [7:0] | Requester Segment（RSV=0 时 Reserved） |
| +1 | [7:0] | PR_Sent_Counter |
| +2 | [7:0] | Stream_ID |
| +3 | [7] | XT |
| +3 | [6:4] | Sub-Stream[2:0] |
| +3 | [3] | RSV（Requester Segment Valid） |
| +3 | [2] | R |
| +3 | [1] | K |
| +3 | [0] | T |

判定要点：

- IDE TLP **必须**包含 OHC-C；
- `Sub-Stream = 000b/001b/010b` → 该 TLP 是 IDE TLP，`PR_Sent_Counter / Stream_ID / K / XT / T` 有意义；
- `Sub-Stream = 111b` → 非 IDE TLP（仅为了携带 Requester Segment），上述字段 Reserved；
- `Sub-Stream = 011b~110b` → 接收方行为未定义；
- IDE Completion 与非 IDE Completion 携带 OHC-C 时 `RSV` 必须为 0；
- 注意：OHC-C 不含 IDE Prefix 中的 M/P 位，FM 下 MAC/PCRC 的有无由 `TS` 表示。

### 3.7 OHC-E（1 / 2 / 4 DW，Figure 2-86 ~ 2-88）

FM 中用 OHC-E 取代 NFM 的 End-End TLP Prefix（E 编码 0011b~1111b 的内容）。

每个 DW 内部格式一致：

| 位 | 字段 |
|---|---|
| byte0[7:4] | 格式码（Entry Type） |
| byte0[3:0] | 当 Entry 为 Prefix 时：`E[3:0]`（取值等同 Table 2-39，但 0000b~0010b Reserved） |
| byte1~3 | 当 Entry 为 Prefix 时：对应 End-End Prefix 的 byte1~3 |

Entry 格式码：

| 编码 | 含义 |
|---|---|
| `0000b` | No Entry（本 DW 其余部分 Reserved） |
| `0001b` | End-End TLP Prefix DW |
| `0010b`~`1111b` | Reserved（接收方按 No Entry 处理） |

规则：OHC-E 必须从第一个 DW 起**无空洞**填充，No Entry 只能出现在末尾；发送方必须用最小尺寸的 OHC-E。

### 3.8 TS[2:0] Trailer 编码（§2.2.1.2）

| TS[2:0] | Trailer |
|---|---|
| `000b` | 无 Trailer |
| `001b` | 1 DW Trailer —— 若存在 OHC-C 且 Sub-Stream 表明是 IDE TLP：内容 Reserved；否则为 **ECRC** |
| `010b` | 1 DW Trailer，内容 Reserved |
| `011b` | 2 DW Trailer，内容 Reserved |
| `100b` | 2 DW Trailer，内容 Reserved |
| `101b` | 3 DW Trailer —— IDE MAC（IDE TLP）或 Reserved |
| `110b` | 4 DW Trailer —— IDE MAC + PCRC（IDE TLP）或 Reserved |
| `111b` | 5 DW Trailer，内容 Reserved |

> 解析器只需按表取长度即可跳过；`001b` 是否含 ECRC 取决于是否 IDE TLP。

### 3.9 FM 头长度判定（核心公式）

```python
header_base_dw = TABLE_TYPE[type8].header_base_dw   # 1..7，来自 Table 2-5
e_dw = {0:0, 1:1, 2:2, 3:4}[ (ohc >> 3) & 0b11 ]
ohc_dw = (ohc & 1) + ((ohc >> 1) & 1) + ((ohc >> 2) & 1) + e_dw
header_total_dw = header_base_dw + ohc_dw
payload_dw = (1024 if length == 0 else length) if has_payload else 0
trailer_dw = {0:0, 1:1, 2:1, 3:2, 4:2, 5:3, 6:4, 7:5}[ts]
tlp_dw = prefix_dw + header_total_dw + payload_dw + trailer_dw
```

### 3.10 Type[7:0] 编码（Table 2-5）—— 已定义条目

| Type | 名称 | FC | 载荷 | Header Base (DW) | 备注 |
|---|---|---|---|---|---|
| 0 | NOP | none | 无 | 1 | 本地终结；仅 Type 有意义 |
| 1 | MRdLk（32b，地址路由） | NPR | 无 | 3 | 1:1 可翻译 |
| 2 | IORd | NPR | 无 | 3 | 1:1 |
| 3 | MRd（32b，地址路由） | NPR | 无 | 3 | NFM 用同一 Type；需改 Type 值 |
| 4 | CfgRd0 | NPR | 无 | 3 | 1:1 |
| 5 | CfgRd1 | NPR | 无 | 3 | 1:1 |
| 10 | Cpl | CPL | 无 | 3 | 1:1 |
| 11 | CplLk | CPL | 无 | 3 | 1:1 |
| 12 | UIOWrCpl | CPL | 无 | 3 | FM 新增 |
| 13 | UIORdCpl | CPL | 无 | 3 | FM 新增 |
| 32 | MRd（64b，地址路由） | NPR | 无 | 4 | 1:1 |
| 33 | MRdLk（64b） | NPR | 无 | 4 | 1:1 |
| 34 | UIOMRd | NPR | 无 | 4 | FM 新增 |
| 48 | Msg（路由到 RC） | PR | 无 | 4 | 1:1 |
| 49 | Msg（按地址 64b 路由） | PR | 无 | 4 | 当前无定义 |
| 50 | Msg（按 ID 路由） | PR | 无 | 4 | 1:1 |
| 51 | Msg（RC 广播） | PR | 无 | 4 | 1:1 |
| 52 | Msg（本地，接收方终结） | PR | 无 | 4 | 1:1 |
| 53 | Msg（PME_TO_Ack 汇聚到 RC） | PR | 无 | 4 | 1:1 |
| 54,55 | Msg（保留） | PR | 无 | 4 | — |
| 64 | MWr（32b） | PR | Length | 3 | 1:1 |
| 66 | IOWr | NPR | Length | 3 | 1:1 |
| 68 | CfgWr0 | NPR | Length | 3 | 1:1 |
| 69 | CfgWr1 | NPR | Length | 3 | 1:1 |
| 72 | UIORdCplD | CPL | Length | 3 | FM 新增 |
| 74 | CplD | CPL | Length | 3 | 1:1 |
| 75 | CplDLk | CPL | Length | 3 | 1:1 |
| 76 | FetchAdd（32b） | NPR | Length | 3 | 1:1 |
| 77 | Swap（32b） | NPR | Length | 3 | 1:1 |
| 78 | CAS（32b） | NPR | Length | 3 | 1:1 |
| 91 | DMWr（32b） | NPR | Length | 3 | 1:1 |
| 96 | MWr（64b） | PR | Length | 4 | 1:1 |
| 97 | UIOMWr | PR | Length | 4 | FM 新增 |
| 108 | FetchAdd（64b） | NPR | Length | 4 | 1:1 |
| 109 | Swap（64b） | NPR | Length | 4 | 1:1 |
| 110 | CAS（64b） | NPR | Length | 4 | 1:1 |
| 112 | MsgD（路由到 RC） | PR | Length | 4 | 1:1 |
| 113 | MsgD（按地址 64b） | PR | Length | 4 | 当前无定义 |
| 114 | MsgD（按 ID） | PR | Length | 4 | 1:1 |
| 115 | MsgD（RC 广播） | PR | Length | 4 | 1:1 |
| 116 | MsgD（本地） | PR | Length | 4 | 1:1 |
| 117 | MsgD（PME_TO_Ack，未使用） | PR | Length | 4 | 1:1 |
| 118,119 | MsgD（保留） | PR | Length | 4 | — |
| 123 | DMWr（64b） | NPR | Length | 4 | 1:1 |
| 141 | FlitModePrefix | none | 无 | 1 | FM 本地前缀 |
| 142 | VendPrefixL0 | none | 无 | 1 | 厂商本地前缀 0 |
| 143 | VendPrefixL1 | none | 无 | 1 | 厂商本地前缀 1 |

> 完整的 0~255 全表（含全部 Reserved 区间及其 Header Base 长度）见 **附录 A**。

---

## 4. 两种模式逐字段对照

| 字段 | NFM 位置 | FM 位置 | 差异 |
|---|---|---|---|
| 格式指示 | `Fmt[2:0]` byte0[7:5] | 无（由 `Type[7:0]` 承担） | FM 取消了 Fmt |
| 类型 | `Type[4:0]` byte0[4:0] | `Type[7:0]` byte0[7:0] | 宽度 5 → 8 |
| TC | byte1[6:4] | byte1[7:5] | 位置左移 1 位 |
| Tag 高位 | `T9` byte1[7] / `T8` byte1[3] | 合并进 Tag 字段（14 bit 连续） | NFM 不连续 |
| Attr | `Attr[1:0]` byte2[5:4] + `A2` byte1[2] | `Attr[2:0]` byte2[4:2] | 合并为连续 3 bit |
| EP | byte2[6] | 类型相关（请求头 byte6[7]） | 位置变化 |
| TD | byte2[7] | 无，改用 `TS[2:0]` | 语义扩展为"尾部大小" |
| TH | byte1[0] | 无（TPH 内容进 OHC-B） | — |
| AT | byte2[3:2] | 地址 DW 的 bit[1:0]（Figure 2-18/2-19） | 位置变化 |
| Length | byte2[1:0]+byte3[7:0] | byte2[1:0]+byte3[7:0] | **相同** |
| 可选扩展 | End-End Prefix（独立 1 DW 单元） | OHC-A/B/C/E | 机制完全不同 |
| 尾保护 | ECRC（TD=1 → 1 DW） | Trailer（TS 指明 0~5 DW，含 IDE MAC/PCRC） | — |

---

## 5. 解析实现指南

### 5.1 判定当前数据属于哪种模式

TLP 字节流本身**不携带模式标志位**（模式由链路协商决定，见 §4.2 Link 状态）。工程做法：

1. **由调用方传入** `mode` 参数（推荐，最可靠）；
2. 若工具要"自动猜"：先按 NFM 尝试解析（校验 `Fmt` 是否为合法值 0~4、`Type` 是否在 Table 2-3 内、`Length` 与剩余字节是否自洽），失败再按 FM 尝试（校验 `Type[7:0]`、`Length`、`OHC`、`TS` 与总长是否自洽）。二者都自洽时以调用方配置为准，并给出告警。

### 5.2 解析流程（伪代码）

```python
def parse_tlp(buf, mode):
    off = 0
    # ---- 1. 前缀 ----
    if mode == "NFM":
        while buf[off] >> 5 == 0b100:          # Fmt == 100b
            yield prefix(buf, off)
            off += 4
            if prefix_count_EE > 4: raise Malformed
    else:  # FM
        while 128 <= buf[off] <= 143:           # Type[7:0] 属于 Local Prefix 区间
            yield prefix(buf, off)
            off += 4

    # ---- 2. 头部字段 ----
    if mode == "NFM":
        b0, b1, b2, b3 = buf[off:off+4]
        fmt   = (b0 >> 5) & 0x7
        type5 =  b0 & 0x1F
        header_dw = 3 + (fmt & 1)
        tc    = (b1 >> 4) & 0x7
        tag9  = (b1 >> 7) & 0x1
        tag8  = (b1 >> 3) & 0x1
        a2    = (b1 >> 2) & 0x1
        th    =  b1 & 0x1
        td    = (b2 >> 7) & 0x1
        ep    = (b2 >> 6) & 0x1
        attr  = ((b2 >> 4) & 0x3) | (a2 << 2)
        at    = (b2 >> 2) & 0x3
        length= ((b2 & 0x3) << 8) | b3
        ohc_dw = 0; ts = 0
    else:  # FM
        b0, b1, b2, b3 = buf[off:off+4]
        type8 = b0
        tc    = (b1 >> 5) & 0x7
        ohc   =  b1 & 0x1F
        ts    = (b2 >> 5) & 0x7
        attr  = (b2 >> 2) & 0x7
        length= ((b2 & 0x3) << 8) | b3
        td = ep = th = 0
        header_dw = TYPE_TABLE_FM[type8].header_base_dw
        ohc_dw = ((ohc & 1) + ((ohc>>1) & 1) + ((ohc>>2) & 1)
                  + {0:0,1:1,2:2,3:4}[ (ohc >> 3) & 0x3 ])

    payload_dw = (1024 if length == 0 else length) if has_payload(type, mode) else 0
    if mode == "NFM":
        trailer_dw = 1 if td else 0
    else:
        trailer_dw = {0:0,1:1,2:1,3:2,4:2,5:3,6:4,7:5}[ts]

    total = header_dw + ohc_dw + payload_dw + trailer_dw   # 单位 DW，不含前缀
    ...
```

### 5.3 长度与偏移速查

| 项 | NFM | FM |
|---|---|---|
| 头（不含前缀） | 3 或 4 DW | 1~7 DW（Header Base）+ 0~7 DW（OHC） |
| 载荷 | `Length`（0 → 1024）DW | 同左 |
| 尾 | `TD ? 1 : 0` DW | 查 TS 表，0~5 DW |
| 前缀 | 每前缀 1 DW，End-End ≤ 4 个 | 每前缀 1 DW（Type 141/142/143） |
| 4 字节对齐 | 必须 | 必须 |

### 5.4 常见实现陷阱

1. **`Length = 0` 表示 1024 DW**，不是 0 —— 写 `payload = length * 4` 会少算 4 KB。
2. **NFM 的 `Tag[9:8]` 不在 Tag 字节里**：`Tag = (T9 << 9) | (T8 << 8) | byte6`，漏掉会导致 Tag 值错。
3. **FM 的 `Attr` 是 3 bit 连续字段**（byte2[4:2]），不要沿用 NFM 的 `Attr[1:0]+A2` 拼法。
4. **FM 的 `AT` 不在首 DW**，而在地址路由类请求的最后一个地址 DW 的 bit[1:0]；解析非地址路由类型时不要强行读。
5. **OHC 是位图不是数量**：`OHC=0b00101` 表示 A + C 两个 OHC（2 DW），不是 5 DW。
6. **OHC 顺序固定 A→B→C→E**，不能按 bit 位从低到高"跳着"读——A、B、C 各 1 DW，E 占最后 1/2/4 DW。
7. **Trailer 不是头部**：ECRC / IDE MAC 位于 payload 之后，计算 header 长度时不能算进去，但计算 TLP 总长时必须算。
8. **FM 下 `Type` 必须完整 8 bit 解码**：即使某编码 Reserved，也要按 Table 2-5 给出的 Header Base 大小跳过（Reserved 条目同样有长度！），否则后续 TLP 全部错位。
9. **NFM `Fmt=100b` 是前缀不是 TLP 头**，必须循环剥离，直到遇到非 100b。
10. **Reserved 字段处理**：读取时忽略、转发时原样保留；解析器不应因 Reserved 位非 0 直接报错，但应给出告警。

### 5.5 合法性校验清单（建议实现）

- [ ] NFM：`Fmt` ∈ {0,1,2,3,4}；`Fmt=4` 时 `Type[4:0]` 属于 Table 2-3 的 LPrfx/EPrfx
- [ ] NFM：End-End Prefix 数量 ≤ 4
- [ ] FM：`Type[7:0]` 在 Table 2-5 内有定义（含 Reserved 条目）
- [ ] FM：`OHC[4:3]` 与 `OHC[2:0]` 组合长度可算；`OHC=00000b` 时不得出现 OHC 数据
- [ ] 计算出的总长 ≤ 缓冲区剩余长度
- [ ] `Length` 与实际剩余字节是否 4 字节对齐
- [ ] `TD=1`（NFM）或 `TS≠0`（FM）时，尾部长度足够
- [ ] Header 内 Reserved 位为 0（告警级，不阻断）

---

## 6. 附录

### 附录 A：FM Type[7:0] 全表（Table 2-5，含 Reserved 区间）

> 解析器必须依赖此表确定 Header Base 长度，即使 Type 为 Reserved。

| Type 范围 | 名称 / 路由 | FC | 载荷 | Base (DW) |
|---|---|---|---|---|
| 0 | NOP（Local，终结） | none | 无 | 1 |
| 1 | MRdLk 32b | NPR | 无 | 3 |
| 2 | IORd | NPR | 无 | 3 |
| 3 | MRd 32b | NPR | 无 | 3 |
| 4-5 | CfgRd0 / CfgRd1 | NPR | 无 | 3 |
| 6-7 | Reserved（ID 路由） | CPL | Length | 4 |
| 8-9 | Reserved（ID 路由） | PR | 无 | 3 |
| 10-11 | Cpl / CplLk | CPL | 无 | 3 |
| 12-13 | UIOWrCpl / UIORdCpl | CPL | 无 | 3 |
| 14-15 | Reserved（ID 路由） | CPL | 无 | 3 |
| 16-19 | Reserved（64b 地址路由） | NPR | Length | 5 |
| 20-21 | Reserved（64b 地址路由） | NPR | Length | 5 |
| 22-23 | Reserved（64b 地址路由） | NPR | Length | 7 |
| 24-25 | Reserved（ID 路由） | CPL | 无 | 7 |
| 26 | Reserved（ID 路由） | CPL | Length | 7 |
| 27 | Reserved（原 Trusted Config Read） | CPL | Length | 7 |
| 28-29 | Reserved（ID 路由） | NPR | 无 | 3 |
| 30-31 | Reserved（ID 路由） | NPR | 无 | 6 |
| 32-33 | MRd / MRdLk 64b | NPR | 无 | 4 |
| 34 | UIOMRd | NPR | 无 | 4 |
| 35 | Reserved（64b 地址路由） | NPR | 无 | 4 |
| 36-39 | Reserved（64b 地址路由） | NPR | 无 | 4 |
| 40-43 | Reserved（ID 路由） | CPL | 无 | 4 |
| 44-45 | Reserved（ID 路由） | PR | 无 | 4 |
| 46-47 | Reserved（ID 路由） | PR | 无 | 5 |
| 48-53 | Msg（无数据，各种路由） | PR | 无 | 4 |
| 54-55 | Msg（保留编码） | PR | 无 | 4 |
| 56-59 | Reserved（64b 地址路由） | NPR | 无 | 4 |
| 60-61 | Reserved（ID 路由） | NPR | 无 | 4 |
| 62-63 | Reserved（ID 路由） | NPR | 无 | 5 |
| 64 | MWr 32b | PR | Length | 3 |
| 65 | Reserved（ID 路由） | PR | Length | 6 |
| 66 | IOWr | NPR | Length | 3 |
| 67 | Reserved（ID 路由） | PR | Length | 6 |
| 68-69 | CfgWr0 / CfgWr1 | NPR | Length | 3 |
| 70-71 | Reserved（ID 路由） | NPR | Length | 3 |
| 72 | UIORdCplD | CPL | Length | 3 |
| 73 | Reserved（ID 路由） | CPL | Length | 3 |
| 74-75 | CplD / CplDLk | CPL | Length | 3 |
| 76-78 | FetchAdd / Swap / CAS 32b | NPR | Length | 3 |
| 79 | Reserved（64b 地址路由） | PR | 无 | 4 |
| 80-83 | Reserved（64b 地址路由） | NPR | Length | 6 |
| 84-85 | Reserved（64b 地址路由） | NPR | Length | 6 |
| 86-87 | Reserved（64b 地址路由） | NPR | Length | 7 |
| 88-89 | Reserved（ID 路由） | PR | Length | 3 |
| 90 | Reserved（64b 地址路由） | PR | Length | 4 |
| 91 | DMWr 32b | NPR | Length | 3 |
| 92-93 | Reserved（ID 路由） | PR | Length | 4 |
| 94-95 | Reserved（ID 路由） | PR | Length | 5 |
| 96 | MWr 64b | PR | Length | 4 |
| 97 | UIOMWr | PR | Length | 4 |
| 98-107 | Reserved（64b 地址路由） | PR | Length | 4 |
| 108-110 | FetchAdd / Swap / CAS 64b | NPR | Length | 4 |
| 111 | Reserved（64b 地址路由） | NPR | Length | 4 |
| 112-117 | MsgD（各种路由） | PR | Length | 4 |
| 118-119 | MsgD（保留编码） | PR | Length | 4 |
| 120-122 | Reserved（64b 地址路由） | NPR | Length | 4 |
| 123 | DMWr 64b | NPR | Length | 4 |
| 124-127 | Reserved（64b 地址路由） | NPR | Length | 4 |
| 128-140 | Reserved（Local Prefix，终结） | none | 无 | 1 |
| 141 | FlitModePrefix | none | 无 | 1 |
| 142-143 | VendPrefixL0 / L1 | none | 无 | 1 |
| 144-147 | Reserved（64b 地址路由） | PR | 无 | 4 |
| 148-151 | Reserved（64b 地址路由） | PR | 无 | 5 |
| 152-155 | Reserved（64b 地址路由） | PR | 无 | 6 |
| 156-159 | Reserved（64b 地址路由） | PR | 无 | 7 |
| 160-167 | Reserved（64b 地址路由） | NPR | 无 | 5 |
| 168-169 | Reserved（ID 路由） | PR | 无 | 6 |
| 170-171 | Reserved（ID 路由） | PR | 无 | 7 |
| 172-173 | Reserved（ID 路由） | CPL | 无 | 5 |
| 174-175 | Reserved（ID 路由） | CPL | 无 | 6 |
| 176-183 | Reserved（64b 地址路由） | PR | Length | 5 |
| 184-191 | Reserved（64b 地址路由） | PR | Length | 5 |
| 192-199 | Reserved（64b 地址路由） | NPR | 无 | 6 |
| 200-201 | Reserved（ID 路由） | NPR | 无 | 7 |
| 202-203 | Reserved（ID 路由） | CPL | Length | 5 |
| 204-205 | Reserved（ID 路由） | CPL | Length | 6 |
| 206-207 | Reserved（ID 路由） | PR | Length | 7 |
| 208-215 | Reserved（64b 地址路由） | PR | Length | 6 |
| 216-223 | Reserved（64b 地址路由） | PR | Length | 6 |
| 224-225 | Reserved（Local，终结） | none | 无 | 4 |
| 226-227 | Reserved（Local，终结） | none | 无 | 6 |
| 228-229 | Reserved（Local，终结） | none | Length | 4 |
| 230-231 | Reserved（Local，终结） | none | Length | 6 |
| 232-239 | Reserved（64b 地址路由） | NPR | 无 | 7 |
| 240-241 | Reserved（ID 路由） | NPR | Length | 4 |
| 242-243 | Reserved（ID 路由） | NPR | Length | 5 |
| 244-245 | Reserved（ID 路由） | NPR | Length | 6 |
| 246-247 | Reserved（ID 路由） | NPR | Length | 7 |
| 248-255 | Reserved（64b 地址路由） | PR | Length | 7 |

补充：

- FC 类型为 `none` 的 TLP（Local Prefix / NOP / 部分 Reserved Local）接收方不必缓存，可静默丢弃。
- Reserved 但 FC 为 PR/NPR 的 Request，建议在更新流控信用后丢弃；FC 为 CPL 的按 Unexpected Completion 处理。
- 「Local … Terminate at Receiver」类条目在接收端口必须丢弃。

### 附录 B：典型 Memory Request 头部布局（供字段偏移核对）

**NFM 32-bit（3 DW，Figure 2-16）**

| DW | 字节 | 内容 |
|---|---|---|
| 0 | 0-3 | `Fmt` `Type` `T9` `TC` `T8` `A2` `R` `TH` `TD` `EP` `Attr[1:0]` `AT` `Length` |
| 1 | 4-5 | Requester ID[15:0] |
| 1 | 6 | Tag[7:0] |
| 1 | 7 | Last DW BE[3:0] \| First DW BE[3:0] |
| 2 | 8-11 | Address[31:2] \| PH[1:0] |

**NFM 64-bit（4 DW，Figure 2-17）**：DW2 = Address[63:32]；DW3 = Address[31:2] \| PH[1:0]。

**FM 32-bit（3 DW，Figure 2-18）**

| DW | 字节 | 内容 |
|---|---|---|
| 0 | 0-3 | `Type[7:0]` `TC` `OHC` `TS` `Attr[2:0]` `Length` |
| 1 | 4-5 | Requester ID[15:0] |
| 1 | 6 | [7] EP \| [6] R \| [5:0] Tag[13:8] |
| 1 | 7 | Tag[7:0] |
| 2 | 8-11 | Address[31:2] \| AT[1:0] |

**FM 64-bit（4 DW，Figure 2-19）**：DW2 = Address[63:32]；DW3 = Address[31:2] \| AT[1:0]。

> 其它类型（Completion / Configuration / Message / AtomicOp）的字节 4 以后内容随类型变化，见 §2.2.5（请求）、§2.2.8（Message）、§2.2.9（Completion）中对应的 Figure。

### 附录 C：机器可读表（Python 片段，可直接搬进工具）

```python
# ---- NFM: Fmt/Type → 头长、是否带数据 ----
# key = (fmt, type4)，value = (name, header_dw, has_data)
NFM_TYPE = {
    (0b000, 0b00000): ("MRd32",   3, False),
    (0b001, 0b00000): ("MRd64",   4, False),
    (0b000, 0b00001): ("MRdLk32", 3, False),
    (0b001, 0b00001): ("MRdLk64", 4, False),
    (0b010, 0b00000): ("MWr32",   3, True),
    (0b011, 0b00000): ("MWr64",   4, True),
    (0b000, 0b00010): ("IORd",    3, False),
    (0b010, 0b00010): ("IOWr",    3, True),
    (0b000, 0b00100): ("CfgRd0",  3, False),
    (0b010, 0b00100): ("CfgWr0",  3, True),
    (0b000, 0b00101): ("CfgRd1",  3, False),
    (0b010, 0b00101): ("CfgWr1",  3, True),
    (0b000, 0b01010): ("Cpl",     3, False),
    (0b010, 0b01010): ("CplD",    3, True),
    (0b000, 0b01011): ("CplLk",   3, False),
    (0b010, 0b01011): ("CplDLk",  3, True),
    (0b010, 0b01100): ("FetchAdd32", 3, True),
    (0b011, 0b01100): ("FetchAdd64", 4, True),
    (0b010, 0b01101): ("Swap32",  3, True),
    (0b011, 0b01101): ("Swap64",  4, True),
    (0b010, 0b01110): ("CAS32",   3, True),
    (0b011, 0b01110): ("CAS64",   4, True),
    (0b010, 0b11011): ("DMWr32",  3, True),
    (0b011, 0b11011): ("DMWr64",  4, True),
    (0b001, 0b10000): ("Msg-RC",       4, False),   # Type = 10rrr
    (0b011, 0b10000): ("MsgD-RC",      4, True),
    # Type[4:3]=10 且 Type[2:0]=r[2:0] 为路由方式，共 8 种，见 Table 2-20
}

# ---- FM: Type[7:0] → (name, header_base_dw, has_data) ----
# 只列已定义条目；Reserved 条目请按附录 A 补齐
FM_TYPE = {
    0:   ("NOP",            1, False),
    1:   ("MRdLk32",        3, False),
    2:   ("IORd",           3, False),
    3:   ("MRd32",          3, False),
    4:   ("CfgRd0",         3, False),
    5:   ("CfgRd1",         3, False),
    10:  ("Cpl",            3, False),
    11:  ("CplLk",          3, False),
    12:  ("UIOWrCpl",       3, False),
    13:  ("UIORdCpl",       3, False),
    32:  ("MRd64",          4, False),
    33:  ("MRdLk64",        4, False),
    34:  ("UIOMRd",         4, False),
    48:  ("Msg-RC",         4, False),
    50:  ("Msg-ID",         4, False),
    51:  ("Msg-Bcast",      4, False),
    52:  ("Msg-Local",      4, False),
    53:  ("Msg-PME_TO_Ack", 4, False),
    64:  ("MWr32",          3, True),
    66:  ("IOWr",           3, True),
    68:  ("CfgWr0",         3, True),
    69:  ("CfgWr1",         3, True),
    72:  ("UIORdCplD",      3, True),
    74:  ("CplD",           3, True),
    75:  ("CplDLk",         3, True),
    76:  ("FetchAdd32",     3, True),
    77:  ("Swap32",         3, True),
    78:  ("CAS32",          3, True),
    91:  ("DMWr32",         3, True),
    96:  ("MWr64",          4, True),
    97:  ("UIOMWr",         4, True),
    108: ("FetchAdd64",     4, True),
    109: ("Swap64",         4, True),
    110: ("CAS64",          4, True),
    112: ("MsgD-RC",        4, True),
    114: ("MsgD-ID",        4, True),
    115: ("MsgD-Bcast",     4, True),
    116: ("MsgD-Local",     4, True),
    117: ("MsgD-PME_TO_Ack",4, True),
    123: ("DMWr64",         4, True),
    141: ("FlitModePrefix", 1, False),
    142: ("VendPrefixL0",   1, False),
    143: ("VendPrefixL1",   1, False),
}

TS_TRAILER_DW = {0:0, 1:1, 2:1, 3:2, 4:2, 5:3, 6:4, 7:5}
OHC_E_DW      = {0:0, 1:1, 2:2, 3:4}     # 索引 = OHC[4:3]
```

### 附录 D：原文定位索引

| 内容 | 章节 | 表/图 | 页码 |
|---|---|---|---|
| 通用字段（含前缀） | §2.2.1 | Figure 2-4 | 157 |
| NFM 通用头位图 | §2.2.1.1 | Figure 2-5 | 158 |
| Fmt 编码 | §2.2.1.1 | Table 2-2 | 158 |
| NFM Fmt/Type 编码 | §2.2.1.1 | Table 2-3 | 158-159 |
| Length 编码 | §2.2.1.1 | Table 2-4 | 160 |
| FM 首 DW 位图 | §2.2.1.2 | Figure 2-6 | 160 |
| FM Type[7:0] 编码 | §2.2.1.2 | Table 2-5 | 162-171 |
| TS 编码 | §2.2.1.2 | 正文列表 | 171-172 |
| OHC 编码 | §2.2.1.2 | 正文列表 | 172 |
| OHC-A 分类 | §2.2.1.2 | Table 2-6 | 172-173 |
| OHC-A1~A5 | §2.2.1.2 | Figure 2-7 ~ 2-11 | 173-174 |
| OHC-B | §2.2.1.2 | Figure 2-12 | 175 |
| OHC-C | §2.2.1.2 | Figure 2-13 | 175 |
| OHC-E1/E2/E4 | §2.2.11 | Figure 2-86 ~ 2-88 | 252-253 |
| Local Prefix 类型 | §2.2.10.2 | Table 2-38 | 249 |
| End-End Prefix 类型 | §2.2.10.4 | Table 2-39 | 250 |
| NFM 32b/64b 地址路由 | §2.2.4.1 | Figure 2-16 / 2-17 | 187 |
| FM 32b/64b 地址路由 | §2.2.4.1 | Figure 2-18 / 2-19 | 188 |

---

## 7. 待补充（建议下一步）

本文档覆盖 §2.2.1 的"通用包头"规则。若要完成完整解析器，还需按类型补齐以下内容（均不在 §2.2.1 内）：

1. 各类型专属字段布局：§2.2.5（Memory/IO/Cfg 请求，Figure 2-16 ~ 2-22）、§2.2.8（Message，Table 2-20 路由 + 各 Message Code 表）、§2.2.9（Completion，Figure 2-4x）。
2. ID 路由字段位置（ARI / 非 ARI）：Table 2-8、Table 2-9。
3. Byte Enables 与长度换算：Table 2-10、Table 2-40、Table 2-41（Lower Address 计算）。
4. TC → VC 映射与流控信用类型：§2.2.6.6、§2.5。
