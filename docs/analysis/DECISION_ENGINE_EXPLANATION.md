# Decision Engine Architecture

## 🧠 **Overview**

The Decision Engine is the **core intelligence** of the prior authorization system. It processes all validation results, policy checks, and medical necessity evaluations to make automated authorization decisions.

## 🏗️ **Architecture Components**

### **1. DecisionEngine Class**
```python
class DecisionEngine:
    """
    Core decision engine for authorization requests.
    
    Generates authorization decisions based on validation results,
    policy compliance, and medical necessity evaluation.
    """
```

**Key Responsibilities:**
- ✅ **Decision Generation** - Makes approve/deny/more-info decisions
- 🔢 **Confidence Scoring** - Calculates decision confidence (0.0-1.0)
- 📝 **Reasoning Generation** - Provides detailed explanations
- 🔑 **Authorization Numbers** - Generates unique auth numbers for approvals
- 📋 **Alternative Procedures** - Suggests alternatives for denials

### **2. DecisionContext**
```python
@dataclass
class DecisionContext:
    """Context information for decision generation."""
    request: AuthorizationRequest
    validation_result: ValidationResult
    policy_result: Optional[PolicyValidationResult] = None
    cms_compliance: Optional[Dict[str, Any]] = None
    medical_necessity: Optional[Dict[str, Any]] = None
```

**Contains all information needed for decision-making:**
- 📄 **Request Details** - Patient info, procedures, diagnosis
- ✅ **Validation Results** - Data format and business rule validation
- 📋 **Policy Results** - Coverage policy compliance
- 🏛️ **CMS Compliance** - Federal guideline adherence
- 🩺 **Medical Necessity** - Clinical justification evaluation

## 🔄 **Decision Flow Process**

### **Step 1: Input Validation**
```python
def generate_decision(
    request: AuthorizationRequest,
    validation_result: ValidationResult,
    policy_result: Optional[PolicyValidationResult] = None,
    comprehensive_validation: Optional[Dict[str, Any]] = None
) -> AuthorizationDecision:
```

**Validates:**
- Request is not None
- Required parameters are present
- Data types are correct

### **Step 2: Context Creation**
```python
context = DecisionContext(
    request=request,
    validation_result=validation_result,
    policy_result=policy_result
)
```

**Assembles all decision factors into a single context object**

### **Step 3: Decision Evaluation**
```python
decision_status, reasoning, confidence_score = self._evaluate_decision(context)
```

**Three-Factor Analysis:**

#### **🟢 Approval Factors**
- ✅ Request meets coverage policy requirements
- ✅ Request complies with CMS guidelines  
- ✅ High medical necessity established
- ✅ All validation checks passed

#### **🔴 Denial Factors**
- ❌ Request does not meet coverage policy requirements
- ❌ Request does not comply with CMS guidelines
- ❌ Insufficient medical necessity demonstrated
- ❌ Validation failures

#### **🟡 More Info Needed Factors**
- ℹ️ Additional clinical documentation required
- ℹ️ Policy requirements need clarification
- ℹ️ Medical necessity needs more evidence

### **Step 4: Decision Logic**
```python
def _resolve_decision_factors(
    approval_factors: List[str],
    denial_factors: List[str], 
    info_needed_factors: List[str],
    reasoning: List[str]
) -> Tuple[DecisionStatus, List[str], float]:
```

**Decision Matrix:**

| Approval Factors | Denial Factors | Info Needed | Decision | Confidence |
|------------------|----------------|-------------|----------|------------|
| ≥ 2 | 0 | Any | **APPROVED** | 0.85+ |
| 1 | 0 | ≥ 1 | **MORE_INFO** | 0.6 |
| 0 | ≥ 1 | Any | **DENIED** | 0.8+ |
| 0 | 0 | ≥ 1 | **MORE_INFO** | 0.6 |

### **Step 5: Decision Finalization**

#### **For APPROVED Requests:**
```python
if decision_status == DecisionStatus.APPROVED:
    authorization_number = self._generate_authorization_number()
    valid_until = datetime.now(timezone.utc) + timedelta(days=30)
```
- 🔑 **Authorization Number**: `auth_20250728_XXXXXXX-XXX`
- ⏰ **Validity**: 30 days from approval
- 📋 **Policy References**: Links to applicable policies

#### **For DENIED Requests:**
```python
if decision_status == DecisionStatus.DENIED:
    alternative_procedures = self.reasoning_engine.generate_alternative_procedures(
        request, reasoning
    )
```
- 🚫 **Denial Reasoning**: Specific reasons for denial
- 🔄 **Alternatives**: Suggested alternative procedures
- 📚 **Policy References**: Relevant policy citations

#### **For MORE_INFO_NEEDED:**
```python
if decision_status == DecisionStatus.MORE_INFO_NEEDED:
    additional_info_needed = self._generate_additional_info_requirements(context)
```
- 📝 **Required Info**: Specific documentation needed
- 💡 **Guidance**: How to provide the information
- ⏱️ **Next Steps**: What happens after submission

## 🎯 **Confidence Scoring**

### **Confidence Calculation:**
```python
def _calculate_confidence_score(
    validation_results: List[ValidationResult],
    policy_results: List[PolicyValidationResult],
    medical_necessity_score: Optional[float] = None
) -> float:
```

**Factors:**
- **Validation Quality** (0.7-1.0): Based on processing time and errors
- **Policy Confidence** (0.0-1.0): From policy validation service
- **Medical Necessity** (0.0-1.0): Clinical justification strength

**Formula:** `confidence = average(all_factor_scores)`

### **Confidence Thresholds:**
- **High Confidence** (0.8+): Strong evidence for decision
- **Moderate Confidence** (0.6-0.8): Reasonable evidence
- **Low Confidence** (0.0-0.6): Weak evidence, may need review

## 🔧 **Key Methods**

### **Decision Generation:**
- `generate_decision()` - Main entry point
- `generate_decision_with_detailed_reasoning()` - Enhanced version with documentation
- `_evaluate_decision()` - Core decision logic
- `_resolve_decision_factors()` - Final decision determination

### **Utility Methods:**
- `_generate_decision_id()` - Creates unique decision IDs
- `_generate_authorization_number()` - Creates auth numbers
- `_collect_policy_references()` - Gathers applicable policies
- `_generate_additional_info_requirements()` - Lists needed documentation

### **Error Handling:**
- `_generate_error_decision()` - Handles system errors gracefully
- Provides user-friendly messages instead of technical errors
- Logs technical details for debugging

## 📊 **Decision Output**

### **AuthorizationDecision Object:**
```python
AuthorizationDecision(
    decision_id="dec_20250728_110923_bd1b44f7",
    request_id="req_2025_8F8A8A", 
    status=DecisionStatus.APPROVED,
    reasoning=[
        "MRI for joint pain meets medical necessity criteria",
        "Procedure is covered under imaging benefits",
        "Prior conservative treatment documented"
    ],
    policy_references=["PAYER_IMAGING_POLICY_2024", "CMS_NCD_220.2"],
    authorization_number="auth_20250728_6B62CCBA-8BB",
    valid_until="2025-08-27T11:09:23.987417Z",
    confidence_score=0.85,
    decided_at="2025-07-28T11:09:23.987417Z"
)
```

## 🚀 **Integration Points**

### **Input Sources:**
1. **ValidationService** → Basic data validation
2. **PolicyValidationService** → Coverage policy checks  
3. **MedicalNecessityEngine** → Clinical justification
4. **CMSComplianceChecker** → Federal guideline compliance

### **Output Destinations:**
1. **TrackingService** → Decision storage and retrieval
2. **NotificationService** → Provider alerts
3. **AuditService** → Compliance logging
4. **Dashboard** → User interface display

## 🎛️ **Configuration**

### **Tunable Parameters:**
```python
# Decision thresholds
self.approval_confidence_threshold = 0.8
self.denial_confidence_threshold = 0.6

# Authorization validity period (30 days)
self.authorization_validity_days = 30
```

### **Customization Points:**
- **Confidence Thresholds** - Adjust decision sensitivity
- **Validity Periods** - Change authorization duration
- **Reasoning Templates** - Customize decision explanations
- **Alternative Procedures** - Configure suggestion logic

The Decision Engine is designed to be **transparent, auditable, and configurable** while providing **consistent, evidence-based decisions** for healthcare prior authorization requests.