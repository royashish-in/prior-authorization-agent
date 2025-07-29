# How the Decision Engine Generates Decisions

## 🔍 **Step-by-Step Decision Generation Process**

### **1. Input Analysis**
When a request comes in, the decision engine receives:
```python
decision = decision_engine.generate_decision(
    request=auth_request,           # Patient/procedure details
    validation_result=validation,   # Data validation results  
    policy_result=policy_result,    # Coverage policy check
    comprehensive_validation=None   # Additional validations
)
```

### **2. Policy Validation Logic**
The **MockPolicyValidationService** uses simple rule-based logic:

```python
# APPROVAL CRITERIA:
if procedure_code in ['73221', '70551', '72148']:  # MRI codes
    if diagnosis_code.startswith('M25'):           # Joint pain codes
        return APPROVED with reasoning:
        - "MRI for joint pain meets medical necessity criteria"
        - "Procedure is covered under imaging benefits" 
        - "Prior conservative treatment documented"

# DENIAL/MORE_INFO CRITERIA:
else:
    return NOT_COVERED with reasoning:
    - "Request requires additional clinical documentation"
    - "Medical necessity criteria need further evaluation"
```

### **3. Decision Factor Collection**
The engine categorizes validation results into three buckets:

#### **🟢 Approval Factors** (Things that support approval)
```python
approval_factors = []

if policy_result.is_covered:
    approval_factors.append("Request meets coverage policy requirements")
    
if cms_compliance.get('is_compliant'):
    approval_factors.append("Request complies with CMS guidelines")
    
if medical_necessity == 'high':
    approval_factors.append("High medical necessity established")
```

#### **🔴 Denial Factors** (Things that require denial)
```python
denial_factors = []

if not policy_result.is_covered:
    denial_factors.append("Request does not meet coverage policy requirements")
    
if not cms_compliance.get('is_compliant'):
    denial_factors.append("Request does not comply with CMS guidelines")
    
if medical_necessity == 'low':
    denial_factors.append("Insufficient medical necessity demonstrated")
```

#### **🟡 Info Needed Factors** (Things that need clarification)
```python
info_needed_factors = []

if policy_result.additional_requirements:
    info_needed_factors.extend(policy_result.additional_requirements)
    
if cms_compliance.get('recommendations'):
    info_needed_factors.extend(cms_compliance.get('recommendations'))
```

### **4. Decision Resolution Logic**
The `_resolve_decision_factors()` method applies this **exact logic**:

```python
def _resolve_decision_factors(approval_factors, denial_factors, info_needed_factors):
    
    # RULE 1: Any denial factors = DENY
    if denial_factors:
        return DENIED, confidence=0.7-0.95
    
    # RULE 2: Too many info needed factors = MORE_INFO_NEEDED  
    if len(info_needed_factors) >= 2:
        return MORE_INFO_NEEDED, confidence=0.8
    
    # RULE 3: Approval factors + minimal info needed = APPROVE
    if approval_factors and len(info_needed_factors) <= 1:
        return APPROVED, confidence=0.8-0.95
    
    # RULE 4: Default fallback = MORE_INFO_NEEDED
    return MORE_INFO_NEEDED, confidence=0.6
```

## 🎯 **Real Example Walkthrough**

### **Scenario: MRI for Shoulder Pain**
```json
{
    "diagnosis_codes": [{"code": "M25.511"}],  // Pain in right shoulder
    "procedure_codes": [{"code": "73221"}],    // MRI upper extremity
    "clinical_notes": "6 months pain, PT failed..."
}
```

### **Step 1: Policy Validation**
```python
# MockPolicyValidationService checks:
procedure_codes = ["73221"]  # ✅ In approved list
diagnosis_codes = ["M25.511"]  # ✅ Starts with M25

# Result:
policy_result = PolicyValidationResult(
    is_covered=True,  # ✅ COVERED!
    reasoning=[
        "MRI for joint pain meets medical necessity criteria",
        "Procedure is covered under imaging benefits", 
        "Prior conservative treatment documented"
    ],
    confidence_score=0.85
)
```

### **Step 2: Factor Collection**
```python
# ✅ APPROVAL FACTORS:
approval_factors = [
    "Request meets coverage policy requirements"  # From policy_result.is_covered=True
]

# ❌ DENIAL FACTORS:
denial_factors = []  # Empty - no denials

# ℹ️ INFO NEEDED FACTORS:  
info_needed_factors = []  # Empty - no additional requirements
```

### **Step 3: Decision Resolution**
```python
# Apply decision rules:
if denial_factors:           # [] - Empty, skip
if len(info_needed_factors) >= 2:  # 0 < 2, skip  
if approval_factors and len(info_needed_factors) <= 1:  # ✅ TRUE!
    return APPROVED, confidence=0.85
```

### **Step 4: Final Decision**
```python
AuthorizationDecision(
    status=APPROVED,
    reasoning=[
        "MRI for joint pain meets medical necessity criteria",
        "Procedure is covered under imaging benefits",
        "Prior conservative treatment documented", 
        "Approval basis: Request meets coverage policy requirements"
    ],
    authorization_number="auth_20250728_XXXXXXX",
    confidence_score=0.85,
    valid_until="2025-08-27T..."
)
```

## 🚫 **Denial Example**

### **Scenario: Uncommon Procedure**
```json
{
    "diagnosis_codes": [{"code": "Z99.999"}],  // Not M25.xxx
    "procedure_codes": [{"code": "99999"}],    // Not in approved list
}
```

### **Step 1: Policy Validation**
```python
# MockPolicyValidationService checks:
procedure_codes = ["99999"]   # ❌ NOT in approved list
diagnosis_codes = ["Z99.999"] # ❌ Does NOT start with M25

# Result:
policy_result = PolicyValidationResult(
    is_covered=False,  # ❌ NOT COVERED!
    reasoning=[
        "Request requires additional clinical documentation",
        "Medical necessity criteria need further evaluation"
    ]
)
```

### **Step 2: Factor Collection**
```python
# ✅ APPROVAL FACTORS:
approval_factors = []  # Empty

# ❌ DENIAL FACTORS:
denial_factors = [
    "Request does not meet coverage policy requirements"  # From is_covered=False
]

# ℹ️ INFO NEEDED FACTORS:
info_needed_factors = [
    "Provide detailed clinical history and examination findings",
    "Document previous treatments attempted and outcomes"
]
```

### **Step 3: Decision Resolution**
```python
# Apply decision rules:
if denial_factors:  # ✅ Has denial factors!
    return DENIED, confidence=0.8
```

## ⚙️ **Key Decision Rules**

### **Rule Priority (in order):**
1. **🔴 DENY** if any denial factors exist
2. **🟡 MORE_INFO** if ≥2 info needed factors  
3. **🟢 APPROVE** if approval factors + ≤1 info needed
4. **🟡 MORE_INFO** as default fallback

### **Confidence Scoring:**
- **DENIED**: 0.7 + (0.1 × number of denial factors)
- **APPROVED**: 0.8 + (0.05 × number of approval factors)  
- **MORE_INFO**: Fixed at 0.6-0.8

### **Authorization Numbers:**
- **Format**: `auth_YYYYMMDD_XXXXXXX-XXX`
- **Generated**: Only for approved requests
- **Validity**: 30 days from approval

## 🔧 **Customization Points**

### **To Change Approval Criteria:**
Edit `MockPolicyValidationService.validate_coverage_policy()`:
```python
# Add new approved procedure codes:
if any(code in ['73221', '70551', '72148', 'NEW_CODE'] for code in procedure_codes):

# Add new approved diagnosis patterns:
if any(code.startswith('M25') or code.startswith('NEW_PATTERN') for code in diagnosis_codes):
```

### **To Adjust Decision Thresholds:**
Edit `_resolve_decision_factors()`:
```python
# Change info needed threshold:
if len(info_needed_factors) >= 3:  # Was 2

# Change confidence scores:
confidence = min(0.99, 0.9 + (len(approval_factors) * 0.02))  # Higher confidence
```

The decision engine uses **deterministic rule-based logic** rather than machine learning, making it **transparent, auditable, and predictable** - essential qualities for healthcare authorization systems.