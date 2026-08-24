Prompt 4. Prompt for Tentative Diagnosis Decision-making
You are a specialist in the field of rare diseases.
You have access to the following context:
- **Online knowledge** (with titles and URLs): {web_diagnosis}
- **LLM-generated diagnoses**: {llm_response}
- **Diagnosis API results**: {diagnosis_api_response}
- **Similar cases**: {similar_case_detailed}
- **Prompt details:** {patient_info}
—
Based on the above and your knowledge, enumerate the **top 5 most likely rare disease diagnoses**
for this patient.
**For each diagnosis, use the following format:**
## **DIAGNOSIS NAME** (Rank #X/5)
### Diagnostic Reasoning:
- Provide 2-3 concise sentences explaining why this rare disease fits the clinical picture.
- Integrate evidence from all available sources (online knowledge, similar cases, LLM outputs, and API
results).
- Support your reasoning with specific, in-text citations in [X] format, referencing the most relevant
sources (including specific similar cases, articles, or diagnostic tools).
- Briefly discuss the pathophysiological basis for the diagnosis, citing relevant literature or case
evidence.
—
**After listing all 5 diagnoses, include a reference section:**
## References:
- Number each reference in the order it is first cited ([1], [2], ...).
- Only include sources you directly cited in your diagnostic reasoning above.
- For each reference, should provide:
a. Source type (e.g., medical guideline, similar case, literature, diagnosis assisent tool...)
b. Use 3-4 sentences to describe of the content and its relevance.
c. For articles or literature, include the title and URL if provided.
- Every in-text citation [X] in your reasoning should correspond to a numbered entry in your reference
list.
- Try to cover as more sources and references.
- Do not repeat!!
—
**Key Instructions:**
1. Always use in-text citations in [X] format, matching only the references you actually cite in your
reasoning.
2. Each diagnosis must be a rare disease (**bolded** using markdown).
3. Rank from most (#1) to least (#5) likely.
4. Integrate information from all provided sources (medical literature, similar cases, and judgement
analyses) wherever appropriate.
5. Do **not** copy or invent references—only include those present in the provided materials



# Prompt 11. Prompt for Case Summarization
Assume you are a doctor experienced in rare disease diagnosis.
Please judge if the two patient cases are likely to be the same disease based on the patient information.
Only output ‘Yes’ or ‘No’.
Patient 1 phenotype: {patient_info}
Patient 2 phenotype: {retrieved_patient_case}