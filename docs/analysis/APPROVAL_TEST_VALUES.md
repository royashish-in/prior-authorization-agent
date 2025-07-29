# Pre-Authorization Approval Test Values

## ✅ **Values That Should Get APPROVED**

### **Patient Demographics:**
```json
{
    "patient_id": "encrypted_patient_approved_001",
    "age": 45,
    "gender": "female", 
    "insurance_id": "encrypted_insurance_approved_001",
    "member_id": "encrypted_member_approved_001"
}
```

### **Diagnosis Codes (Use ANY of these):**
- **M25.511** - Pain in right shoulder ✅
- **M25.512** - Pain in left shoulder ✅  
- **M25.519** - Pain in unspecified shoulder ✅
- **M25.521** - Pain in right elbow ✅
- **M25.531** - Pain in right wrist ✅

### **Procedure Codes (Use ANY of these):**
- **73221** - MRI upper extremity without contrast ✅
- **70551** - MRI brain without contrast ✅
- **72148** - MRI lumbar spine without contrast ✅

### **Required Fields:**
```json
{
    "provider_id": "prov_12345",
    "procedure_type": "mri",
    "urgency_level": "routine",
    "clinical_notes": "Patient presents with chronic pain lasting 6+ months. Conservative treatment with physical therapy and NSAIDs attempted for 8+ weeks without significant improvement. Physical examination reveals limited range of motion. MRI needed to evaluate for structural damage and guide treatment planning. Patient has documented failed conservative therapy and meets medical necessity criteria."
}
```

## 🔄 **How to Test in Frontend:**

1. **Login:** `provider1` / `provider123`
2. **Go to:** "Submit New Request" tab
3. **Fill in the form with these exact values:**
   - **Provider ID:** `prov_12345`
   - **Patient Age:** `45`
   - **Patient Gender:** `female`
   - **Diagnosis Code:** `M25.511`
   - **Diagnosis Description:** `Pain in right shoulder`
   - **Procedure Code:** `73221`
   - **Procedure Description:** `MRI upper extremity without contrast`
   - **Clinical Notes:** Use the clinical notes example above
   - **Procedure Type:** `MRI`
   - **Urgency Level:** `Routine`

4. **Submit** and you should see **"approved"** status!

## 🚫 **Values That Will Get DENIED:**

Any combination NOT matching the approved patterns above will result in:
- Status: "more_info_needed" or "denied"
- Reasoning: "Request requires manual policy review"

## 🧪 **Quick Test Command:**
```bash
python test_successful_preauth.py
```

This will automatically test the approval scenario and show you the results!