import base64
import json
import re
import tempfile
import streamlit as st
from fpdf import FPDF
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

st.set_page_config(page_title="Food Label AI", layout="wide")

st.title("🥫 Food Label AI")
st.write("Upload a food label image and extract all visible text.")

text_llm = ChatOllama(
    model="qwen3:8b",
    reasoning=False
)

def parse_value(val_str):
    if not val_str or str(val_str).strip() == "":
        return None
    match = re.search(r"([0-9]*\.?[0-9]+)", str(val_str))
    if match:
        return float(match.group(1))
    return None

def get_per_100_value(nutrient_dict, serving_size_val):
    if not nutrient_dict:
        return None
        
    per_100 = parse_value(nutrient_dict.get("per_100g_ml"))
    if per_100 is not None:
        return per_100
        
    per_serving = parse_value(nutrient_dict.get("per_serving"))
    if per_serving is not None and serving_size_val and serving_size_val > 0:
        return round((per_serving / serving_size_val) * 100, 2)
        
    return None

def clean_for_pdf(text):
    if not text:
        return ""
    return str(text).encode('latin-1', 'ignore').decode('latin-1').strip()

def evaluate_nutrient(name, value, product_type="Solid"):
    if value is None: 
        return "⚪ Unavailable", "gray"
        
    if name == "sugar":
        if product_type == "Beverage":
            if value <= 2.5: return "🟢 Low", "green"
            elif value <= 11.25: return "🟡 Moderate", "orange"
            else: return "🔴 High", "red"
        else: # Solid
            if value <= 5.0: return "🟢 Low", "green"
            elif value <= 22.5: return "🟡 Moderate", "orange"
            else: return "🔴 High", "red"
            
    elif name == "sodium":
        if product_type == "Beverage":
            if value <= 120: return "🟢 Low", "green" 
            elif value <= 300: return "🟡 Moderate", "orange"
            else: return "🔴 High", "red"
        else: # Solid   
            if value <= 120: return "🟢 Low", "green"
            elif value <= 600: return "🟡 Moderate", "orange"
            else: return "🔴 High", "red"
            
    elif name == "saturated_fat":
        if product_type == "Beverage":
            if value <= 0.75: return "🟢 Low", "green"
            elif value <= 2.5: return "🟡 Moderate", "orange"
            else: return "🔴 High", "red"
        else: # Solid
            if value <= 1.5: return "🟢 Low", "green"
            elif value <= 5.0: return "🟡 Moderate", "orange"
            else: return "🔴 High", "red"
            
    return "⚪ Unavailable", "gray"

def evaluate_trans_fat(value, ingredients):
    ingredients_text = " ".join(ingredients).lower()
    if value is not None and value > 0:
        return "🔴 High (Avoid)", "red"
    if "partially hydrogenated" in ingredients_text:
        return "🔴 High (Avoid)", "red"
    if value is None:
        return "⚪ Unavailable", "gray"
    return "🟢 Low", "green"

def calculate_overall_risk(assessments):
    statuses = [a["status"] for a in assessments.values()]
    if any("🔴" in s for s in statuses):
        return "🔴 HIGH RISK", "red"
    elif any("🟡" in s for s in statuses):
        return "🟡 MODERATE RISK", "orange"
    elif any("⚪" in s for s in statuses):
        return "⚪ INCOMPLETE DATA", "gray"
    else:
        return "🟢 LOW RISK", "green"

def validate_numeric_integrity(original_json, normalized_json):
    keys_to_check = ["total_sugars", "sodium", "saturated_fat", "trans_fat"]
    orig_nut = original_json.get("nutrition", {})
    norm_nut = normalized_json.get("nutrition", {})
    
    for key in keys_to_check:
        orig_val = parse_value(orig_nut.get(key, {}).get("per_100g_ml"))
        norm_val = parse_value(norm_nut.get(key, {}).get("per_100g_ml"))
        
        if orig_val != norm_val:
            return False, key
    return True, None

def generate_pdf_report(json_data, product_type, overall_risk, assessment_data, explanation):
    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("Arial", style="B", size=16)
    pdf.cell(200, 10, txt="Food Label Risk Assessment Report", ln=True, align="C")
    pdf.ln(5)
    
    brand = json_data.get("brand", "Unknown Brand")
    name = json_data.get("product_name", "Unknown Product")
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(200, 8, txt=f"Product: {clean_for_pdf(brand)} - {clean_for_pdf(name)}", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 8, txt=f"Product Type: {product_type} (Evaluated using UK FSA Guidelines)", ln=True)
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(200, 8, txt=f"Overall Risk: {clean_for_pdf(overall_risk)}", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(200, 8, txt="Nutrient Risk (per 100g/ml):", ln=True)
    pdf.set_font("Arial", size=12)
    for nutrient, data in assessment_data.items():
        val = data['value'] if data['value'] is not None else "N/A"
        stat = clean_for_pdf(data['status'])
        pdf.cell(200, 8, txt=f"- {nutrient}: {val} -> {stat}", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(200, 8, txt="AI Health Explanation:", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 8, txt=clean_for_pdf(explanation))
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        with open(tmp.name, "rb") as f:
            return f.read()

uploaded_file = st.file_uploader(
    "Choose an image", 
    type=["png", "jpg", "jpeg"]
)

if uploaded_file:
    col1, col2 = st.columns(2)

    with col1:
        st.image(uploaded_file, caption="Uploaded Image", use_container_width=True)

    if st.button("Analyze the item"):
        with st.spinner("Reading image..."):
            image_bytes = uploaded_file.read()
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")

            vision_llm = ChatOllama(
                model="qwen2.5vl:7b",
                temperature=0
            )

            message = HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": """
You are an expert food label information extractor.
Extract the information from the food label and return ONLY valid JSON.

Rules:
- Do not explain or summarize.
- Do not wrap the JSON inside ```json.
- If a field is missing, return an empty string.
- Preserve numbers and units exactly as written.
- Determine if the product is a "Solid" or "Beverage" based on the label.

Return JSON in this format:
{
  "product_name": "",
  "brand": "",
  "product_type": "", 
  "serving_size": "",
  "servings_per_pack": "",
  "nutrition": {
    "energy": { "per_100g_ml": "", "per_serving": "" },
    "carbohydrate": { "per_100g_ml": "", "per_serving": "" },
    "total_sugars": { "per_100g_ml": "", "per_serving": "" },
    "added_sugars": { "per_100g_ml": "", "per_serving": "" },
    "dietary_fiber": { "per_100g_ml": "", "per_serving": "" },
    "protein": { "per_100g_ml": "", "per_serving": "" },
    "total_fat": { "per_100g_ml": "", "per_serving": "" },
    "saturated_fat": { "per_100g_ml": "", "per_serving": "" },
    "trans_fat": { "per_100g_ml": "", "per_serving": "" },
    "sodium": { "per_100g_ml": "", "per_serving": "" }
  },
  "ingredients": [],
  "claims": [],
  "manufacturer": "",
  "address": "",
  "fssai_license": "",
  "other_text": ""
}
"""
                    },
                    {
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{image_base64}"
                    }
                ]
            )

            response = vision_llm.invoke([message])

            with col2:
                try:
                    extracted_json = json.loads(response.content)
                    
                    prompt = f"""
You are a Food Label Semantic Normalization Assistant.

Normalize the following JSON.

Rules:
- Normalize ingredient names to their common canonical names.
- Normalize INS/E additive codes to their common names.
- Standardize capitalization and spacing.
- Standardize unit formatting (e.g., "8.5mg" -> "8.5 mg").
- DO NOT alter any numeric nutritional values.
- Preserve the JSON structure exactly.
- Return ONLY valid JSON.

JSON:
{json.dumps(extracted_json, indent=2)}
"""
                    # CHANGE: Catch all exceptions during normalization LLM call
                    try:
                        response1 = text_llm.invoke(prompt)
                        normalized_json = json.loads(response1.content)
                        
                        is_valid, failed_key = validate_numeric_integrity(extracted_json, normalized_json)
                        if not is_valid:
                            st.warning(f"⚠️ Normalization engine hallucinated on '{failed_key}'. Reverting to raw extracted data to ensure safety.")
                            normalized_json = extracted_json
                            
                    except Exception as e:
                        st.warning("⚠️ Normalization engine unavailable or returned invalid formatting. Using raw extracted data.")
                        normalized_json = extracted_json
                    
                    nut = normalized_json.get("nutrition", {})
                    ingredients = normalized_json.get("ingredients", [])
                    product_type = normalized_json.get("product_type", "Solid")
                    if product_type not in ["Solid", "Beverage"]:
                        product_type = "Solid" 
                        
                    serving_size_val = parse_value(normalized_json.get("serving_size"))
                    
                    sugar_val = get_per_100_value(nut.get("total_sugars", {}), serving_size_val)
                    sodium_val = get_per_100_value(nut.get("sodium", {}), serving_size_val)
                    sat_fat_val = get_per_100_value(nut.get("saturated_fat", {}), serving_size_val)
                    trans_fat_val = get_per_100_value(nut.get("trans_fat", {}), serving_size_val)
                    
                    sugar_stat, sugar_color = evaluate_nutrient("sugar", sugar_val, product_type)
                    sodium_stat, sodium_color = evaluate_nutrient("sodium", sodium_val, product_type)
                    sat_fat_stat, sat_fat_color = evaluate_nutrient("saturated_fat", sat_fat_val, product_type)
                    trans_fat_stat, trans_fat_color = evaluate_trans_fat(trans_fat_val, ingredients)
                    
                    assessment_data = {
                        "Sugar": {"value": sugar_val, "status": sugar_stat, "color": sugar_color},
                        "Sodium": {"value": sodium_val, "status": sodium_stat, "color": sodium_color},
                        "Saturated Fat": {"value": sat_fat_val, "status": sat_fat_stat, "color": sat_fat_color},
                        "Trans Fat": {"value": trans_fat_val, "status": trans_fat_stat, "color": trans_fat_color}
                    }
                    
                    overall_risk, overall_color = calculate_overall_risk(assessment_data)

                    explanation_prompt = f"""
Based ONLY on UK FSA Traffic-Light guidelines, give a very brief (3-4 sentences) health assessment of this food product. 
Do not mention WHO or World Health Organization. Do not use markdown formatting. Be direct and user-friendly. Do not calculate risk, just explain the provided data.

Product Type: {product_type}
Overall Risk: {overall_risk}
- Sugar: {sugar_val if sugar_val is not None else 'N/A'} ({sugar_stat})
- Sodium: {sodium_val if sodium_val is not None else 'N/A'} ({sodium_stat})
- Saturated Fat: {sat_fat_val if sat_fat_val is not None else 'N/A'} ({sat_fat_stat})
- Trans Fat: {trans_fat_val if trans_fat_val is not None else 'N/A'} ({trans_fat_stat})
"""
                    
                    # CHANGE: Protect AI Explanation generation from crashes
                    try:
                        explanation_response = text_llm.invoke(explanation_prompt)
                        ai_explanation = explanation_response.content.strip()
                    except Exception as e:
                        ai_explanation = "AI explanation unavailable — please refer to the nutrient assessment above."

                    st.subheader("📊 Health Risk Dashboard")
                    st.markdown(f"### Overall Risk: :{overall_color}[{overall_risk}]")
                    st.caption(f"Evaluated as a **{product_type}** using UK FSA Traffic Light guidelines.")
                    
                    st.write("---")
                    st.markdown("#### 🚦 Nutrient Risk (per 100g/ml)")
                    
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Sugar", f"{sugar_val} g" if sugar_val is not None else "N/A", sugar_stat)
                    c2.metric("Sodium", f"{sodium_val} mg" if sodium_val is not None else "N/A", sodium_stat)
                    c3.metric("Saturated Fat", f"{sat_fat_val} g" if sat_fat_val is not None else "N/A", sat_fat_stat)
                    c4.metric("Trans Fat", f"{trans_fat_val} g" if trans_fat_val is not None else "N/A", trans_fat_stat)
                    
                    st.write("---")
                    st.markdown("#### ℹ️ Informational Data")
                    
                    calories = nut.get("energy", {}).get("per_100g_ml", "N/A")
                    protein = nut.get("protein", {}).get("per_100g_ml", "N/A")
                    fiber = nut.get("dietary_fiber", {}).get("per_100g_ml", "N/A")
                    serving = normalized_json.get("serving_size", "N/A")
                    
                    i1, i2, i3, i4 = st.columns(4)
                    i1.metric("Calories", calories)
                    i2.metric("Protein", protein)
                    i3.metric("Dietary Fiber", fiber)
                    i4.metric("Serving Size", serving)
                    
                    st.write("---")
                    st.markdown("#### 🤖 AI Health Explanation")
                    st.info(ai_explanation)
                    
                    st.write("---")
                    pdf_bytes = generate_pdf_report(
                        normalized_json, 
                        product_type, 
                        overall_risk, 
                        assessment_data, 
                        ai_explanation
                    )
                    
                    st.download_button(
                        label="📄 Download Assessment as PDF",
                        data=pdf_bytes,
                        file_name="Food_Label_Assessment.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

                except json.JSONDecodeError:
                    st.subheader("Model Output (Raw Text)")
                    st.warning("Vision model response was not valid JSON. Please try another image.")
                    st.text(response.content)