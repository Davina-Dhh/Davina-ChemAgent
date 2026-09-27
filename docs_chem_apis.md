# PubChem / ChEMBL 调用说明

免费 REST，**无需 API Key**。封装：`chem_apis.py`。

## 1. 网页（推荐）

1. 打开 http://localhost:8502  
2. 进入 **「分子库查询」**  
3. 输入：中文名 / 英文名 / SMILES / `CHEMBL25`  
4. 勾选 PubChem / ChEMBL → **开始查询**  
5. 可点「用作原料 A/B」转到反应预测  

## 2. 命令行

```powershell
cd G:\Project\DHH\chemcrow-lab

.\.venv\Scripts\python.exe chem_apis.py aspirin
.\.venv\Scripts\python.exe chem_apis.py 阿司匹林
.\.venv\Scripts\python.exe chem_apis.py CHEMBL25
.\.venv\Scripts\python.exe chem_apis.py c1ccccc1Br
```

## 3. Python 调用

```python
from chem_apis import pubchem_lookup, chembl_lookup, lookup_both, chembl_similarity

# PubChem：CID、SMILES、分子量、同义词、页面链接
pc = pubchem_lookup("aspirin")
# pc["ok"], pc["cid"], pc["smiles"], pc["mw"], pc["url"], pc["synonyms"]

# ChEMBL：分子 ID、相似物、活性记录
ch = chembl_lookup("aspirin")           # 名称
ch = chembl_lookup("CHEMBL25")          # ID
ch = chembl_lookup("CC(=O)Oc1ccccc1C(=O)O")  # SMILES
# ch["chembl_id"], ch["similar"], ch["activities"], ch["url"]

# 一次查两边
both = lookup_both("溴苯")

# 只要相似分子（必须是 SMILES）
hits = chembl_similarity("c1ccccc1Br", cutoff=80, limit=10)
```

## 4. 原始 HTTP（等价示例）

**PubChem**

```text
https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/aspirin/cids/JSON
https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/property/CanonicalSMILES,MolecularWeight/JSON
https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/synonyms/JSON
```

**ChEMBL**

```text
https://www.ebi.ac.uk/chembl/api/data/molecule/search.json?q=aspirin
https://www.ebi.ac.uk/chembl/api/data/molecule/CHEMBL25.json
https://www.ebi.ac.uk/chembl/api/data/similarity/CCO/80.json
https://www.ebi.ac.uk/chembl/api/data/activity.json?molecule_chembl_id=CHEMBL25&limit=10
```

## 5. 注意

| 点 | 说明 |
|----|------|
| Key | 不需要 |
| PubChem 限流 | ≤5 次/秒；忙时会 503，模块会自动重试 |
| 中文名 | PubChem 不一定有；可先英文名或本地点「解析」 |
| 用途 | **查库**（结构/性质/活性），不是反应预测模型 |

更完整说明也在页面「说明」页签。
