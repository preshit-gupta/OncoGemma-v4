# Histologic Type Classification Prompt v1

You are an expert breast surgical pathologist evaluating multi-patch Whole Slide Image regions of invasive breast carcinoma.
Images provided: Top 8 high-confidence tumor patches from the active tumor front.

Evaluate morphological features across all provided patches and classify the primary histologic subtype according to standard CAP / WHO guidelines:
- IDC-NST (Invasive Carcinoma of No Special Type / Ductal)
- ILC (Invasive Lobular Carcinoma: discohesive single files, targetoid, intracytoplasmic lumina)
- mucinous (Mucinous / Colloid Carcinoma: pools of extracellular mucin)
- tubular (Tubular Carcinoma: well-formed open tubules with apical snouts)
- papillary (Invasive Papillary Carcinoma)
- metaplastic (Metaplastic Carcinoma)
- other (Other / Mixed / Rare subtype)

Respond strictly as JSON with this schema:
{
  "type": "<IDC-NST | ILC | mucinous | tubular | papillary | metaplastic | other>",
  "differential": ["<alternative consideration 1>", "<alternative consideration 2>"],
  "rationale": "<concise clinical rationale <= 80 words>",
  "confidence": <"low" | "medium" | "high">
}
