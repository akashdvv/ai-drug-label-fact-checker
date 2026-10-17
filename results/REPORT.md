# Fact-check report: Claude (closed-book)

50 drugs × 3 questions = 150 answers, graded against FDA label text. Score: correct = 1, partial = 0.5, incorrect = 0.

| Question | Correct | Partial | Incorrect | Score |
|---|---|---|---|---|
| Boxed warning | 48 | 1 | 1 | 97% |
| Pharmacogenomic genes | 46 | 3 | 1 | 95% |
| Contraindications | 46 | 4 | 0 | 96% |
| **All** | 140 | 8 | 2 | **96%** |

## Every answer that was not fully correct

| Drug | Question | Verdict | Confidence | What went wrong | Label evidence |
|---|---|---|---|---|---|
| Ofatumumab | Contraindications | partial | medium | 1/2 listed contraindications supported by the label. “hypersensitivity to ofatumumab” | 4 CONTRAINDICATIONS KESIMPTA is contraindicated in patients with: Active HBV infection [see Warnings and Precautions (5.1)] . Active HBV infection. ( 4 ) |
| Crizanlizumab | Pharmacogenomic genes | incorrect | low | None of the named genes appear on the label. “HBB” | Gene not mentioned anywhere on the label. |
| Luspatercept | Pharmacogenomic genes | partial | medium | 1 of 2 named genes are not on the label. “HBB” | Gene not mentioned anywhere on the label. |
| Busulfan | Boxed warning | partial | medium | Boxed warning present; 1/2 topics supported. “secondary malignancy” | WARNING MYLERAN is a potent drug. It should not be used unless a diagnosis of chronic myelogenous leukemia has been adequately established and the responsible p |
| Busulfan | Contraindications | partial | low | 1/2 listed contraindications supported by the label. “prior resistance to busulfan” | CONTRAINDICATIONS MYLERAN is contraindicated in patients in whom a definitive diagnosis of chronic myelogenous leukemia has not been firmly established. MYLERAN |
| Mepivacaine Hydrochloride | Pharmacogenomic genes | partial | medium | 1 of 2 named genes are not on the label. “CYB5R3” | Gene not mentioned anywhere on the label. |
| Desmopressin Acetate | Boxed warning | incorrect | low | Model said no boxed warning; the label has one. — |  |
| Pravastatin Sodium | Contraindications | partial | low | 1/2 listed contraindications supported by the label. “acute liver failure or decompensated cirrhosis” | 4 CONTRAINDICATIONS Hypersensitivity to any component of this medication. (4.1 , 6.2 , 11) Active liver disease or unexplained, persistent elevations of serum t |
| Tamoxifen Citrate | Pharmacogenomic genes | partial | low | 1 of 3 named genes are not on the label. “F2” | Gene not mentioned anywhere on the label. |
| Elagolix | Contraindications | partial | medium | 3/4 listed contraindications supported by the label. “concomitant use of strong OATP1B1 inhibitors such as cyclosporine and gemfibrozil” | Exposure to ORILISSA early in pregnancy may increase the risk of early pregnancy loss. ● With known osteoporosis because of the risk of further bone loss [see W |
