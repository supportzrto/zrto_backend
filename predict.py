# import pandas as pd
# import pickle
# import numpy as np

# import os
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# model       = pickle.load(open(os.path.join(BASE_DIR, "my_final_rto_prediction_model.pkl"), "rb"))
# pincode_map = pickle.load(open(os.path.join(BASE_DIR, "pincode_risk.pkl"), "rb"))
# courier_map = pickle.load(open(os.path.join(BASE_DIR, "courier_risk.pkl"), "rb"))
# city_map    = pickle.load(open(os.path.join(BASE_DIR, "city_risk.pkl"), "rb"))
# device_map  = pickle.load(open(os.path.join(BASE_DIR, "device_risk.pkl"), "rb"))
# channel_map = pickle.load(open(os.path.join(BASE_DIR, "channel_risk.pkl"), "rb"))
# day_map     = pickle.load(open(os.path.join(BASE_DIR, "day_risk.pkl"), "rb"))

# # ================= LOAD MODELS =================
# # model = pickle.load(open("my_final_rto_prediction_model.pkl", "rb"))
# # pincode_map = pickle.load(open("pincode_risk.pkl", "rb"))
# # courier_map = pickle.load(open("courier_risk.pkl", "rb"))
# # city_map = pickle.load(open("city_risk.pkl", "rb"))
# # device_map = pickle.load(open("device_risk.pkl", "rb"))
# # channel_map = pickle.load(open("channel_risk.pkl", "rb"))
# # day_map = pickle.load(open("day_risk.pkl", "rb"))

# # ================= COLUMN MAPPING =================
# def smart_column_mapping(df):
#     mapping = {}

#     for col in df.columns:
#         col_lower = col.lower().strip()

#         if ("order" in col_lower and ("id" in col_lower or "number" in col_lower)) or col_lower == "id":
#             mapping[col] = "order_id"
#         elif "amount" in col_lower or "value" in col_lower or "price" in col_lower:
#             mapping[col] = "order_value"
#         elif "payment" in col_lower or "mode" in col_lower:
#             mapping[col] = "payment_type"
#         elif "pin" in col_lower or "zip" in col_lower:
#             mapping[col] = "pincode"
#         elif "hour" in col_lower or "time" in col_lower:
#             mapping[col] = "order_hour"
#         elif "day" in col_lower and "delivery" not in col_lower:
#             mapping[col] = "order_day"
#         elif "city" in col_lower:
#             mapping[col] = "customer_city"
#         elif "state" in col_lower:
#             mapping[col] = "state"
#         elif "device" in col_lower:
#             mapping[col] = "device_type"
#         elif "channel" in col_lower:
#             mapping[col] = "order_channel"
#         elif "previous" in col_lower or "total_orders" in col_lower:
#             mapping[col] = "num_previous_orders"
#         elif "past_cod" in col_lower or "cod_orders" in col_lower:
#             mapping[col] = "past_cod_orders"
#         elif "attempt" in col_lower:
#             mapping[col] = "payment_attempts"
#         elif "delivery" in col_lower:
#             mapping[col] = "estimated_delivery_days"
#         elif "rto" in col_lower:
#             mapping[col] = "past_rto_count"
#         elif "courier" in col_lower or "logistics" in col_lower:
#             mapping[col] = "courier"
#         elif "address" in col_lower:
#             mapping[col] = "address_quality"
#         elif "category" in col_lower or "product" in col_lower:
#             mapping[col] = "product_category"
#         elif "phone" in col_lower:
#             mapping[col] = "customer_phone"

#     return df.rename(columns=mapping)

# # ================= ENSURE COLUMNS =================
# def ensure_columns(df):
#     defaults = {
#         "payment_attempts": 1,
#         "num_previous_orders": 0,
#         "past_rto_count": 0,
#         "past_cod_orders": 0,
#         "estimated_delivery_days": 5,
#         "address_quality": 2,
#         "order_hour": 12,
#         "order_day": "Mon",
#         "courier": "Unknown",
#         "device_type": "Mobile",
#         "order_channel": "Website",
#     }

#     for col, val in defaults.items():
#         if col not in df.columns:
#             df[col] = val

#     return df

# # ================= TRANSFORM =================
# def transform_columns(df):

#     df["address_quality"] = pd.to_numeric(df["address_quality"], errors="coerce").fillna(2)

#     if "payment_type" in df.columns:
#         df["is_cod"] = (df["payment_type"].astype(str).str.upper() == "COD").astype(int)

#     numeric_cols = [
#         "past_cod_orders", "past_rto_count", "order_value",
#         "pincode", "payment_attempts", "num_previous_orders",
#         "estimated_delivery_days", "order_hour"
#     ]

#     for col in numeric_cols:
#         df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

#     return df

# # ================= FEATURE ENGINEERING =================
# def feature_engineering(df):

#     df["is_high_value"] = (df["order_value"] > 3000).astype(int)
#     df["cod_high_value"] = ((df["is_cod"] == 1) & (df["is_high_value"] == 1)).astype(int)
#     df["many_payment_attempts"] = (df["payment_attempts"] > 2).astype(int)
#     df["previous_rto_flag"] = (df["past_rto_count"] > 0).astype(int)
#     df["rto_rate_customer"] = df["past_rto_count"] / (df["num_previous_orders"] + 1)
#     df["is_new_customer"] = (df["num_previous_orders"] == 0).astype(int)

#     return df

# # ================= APPLY MAPS =================
# def apply_risk_maps(df):
#     df["pincode_risk"] = df["pincode"].map(pincode_map)
#     df["courier_performance"] = df["courier"].map(courier_map)
#     df["city_risk"] = df["customer_city"].map(city_map)
#     df["device_risk"] = df["device_type"].map(device_map)
#     df["channel_risk"] = df["order_channel"].map(channel_map)
#     df["day_risk"] = df["order_day"].map(day_map)

#     df.fillna(0.5, inplace=True)
#     return df

# # ================= SANITIZE =================
# def sanitize_for_model(df):
#     for col in df.columns:
#         df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
#     return df

# # ================= EXPLAINABILITY =================
# def generate_reasons(row):
#     reasons = []

#     if row["past_rto_count"] >= 2:
#         reasons.append("High past RTO history")

#     if row["pincode_risk"] > 0.7:
#         reasons.append("High-risk pincode")

#     if row["order_value"] > 1500:
#         reasons.append("High order value")

#     if row["is_new_customer"] == 1:
#         reasons.append("New customer")

#     if row["many_payment_attempts"] == 1:
#         reasons.append("Multiple payment attempts")

#     return ", ".join(reasons) if reasons else "Low risk profile"

# # ================= SAVINGS =================
# def calculate_savings(df):
#     high_df = df[df["risk_level"] == "HIGH"]
#     total_value = high_df["order_value"].sum()

#     rto_rate = 0.6
#     prevention = 0.5

#     savings = total_value * rto_rate * prevention
#     return round(savings)

# # ================= MAIN =================
# def predict_orders(input_file, output_file):

#     df = pd.read_csv(input_file)
#     df.columns = df.columns.str.lower().str.strip()

#     df = smart_column_mapping(df)
#     df = df.loc[:, ~df.columns.duplicated()]
#     df = ensure_columns(df)
#     df = transform_columns(df)
#     df = feature_engineering(df)
#     df = apply_risk_maps(df)

#     features = [
#         'is_cod','is_new_customer','previous_rto_flag',
#         'many_payment_attempts','cod_high_value',
#         'order_value','estimated_delivery_days',
#         'address_quality','rto_rate_customer',
#         'pincode_risk','courier_performance',
#         'city_risk','device_risk','channel_risk','day_risk'
#     ]

#     X = sanitize_for_model(df[features])

#     # ================= PREDICT =================
#     probs = model.predict_proba(X)[:, 1]
#     df["risk_score"] = probs

#     # ================= DYNAMIC THRESHOLDS =================
#     high_th = np.percentile(probs, 75)
#     med_th = np.percentile(probs, 40)

#     def get_risk(score):
#         if score >= high_th:
#             return "HIGH"
#         elif score >= med_th:
#             return "MEDIUM"
#         else:
#             return "LOW"

#     df["risk_level"] = df["risk_score"].apply(get_risk)

#     # ================= DECISION =================
#     def decision(row):
#         if row["risk_level"] == "HIGH":
#             return "BLOCK_COD"
#         elif row["risk_level"] == "MEDIUM":
#             return "VERIFY"
#         else:
#             return "ALLOW"

#     df["decision"] = df.apply(decision, axis=1)

#     # ================= ACTION =================
#     def action(row):
#         if row["risk_level"] == "HIGH":
#             return "Block COD" if row["order_value"] > 1500 else "Convert to Prepaid"
#         elif row["risk_level"] == "MEDIUM":
#             return "Call / WhatsApp"
#         else:
#             return "Proceed"

#     df["action"] = df.apply(action, axis=1)

#     # ================= OFFERS =================
#     df["offer"] = df["risk_level"].map({
#         "HIGH": "10% OFF",
#         "MEDIUM": "5% OFF",
#         "LOW": "No"
#     })

#     df["priority"] = df["risk_level"]

#     # ================= EXPLAIN =================
#     df["reasons"] = df.apply(generate_reasons, axis=1)

#     # ================= SAVINGS =================
#     savings = calculate_savings(df)

#     print(f"\n💰 Estimated Savings: ₹{savings}")

#     # ================= OUTPUT =================
#     final_cols = [
#         "order_id","order_value","risk_score","risk_level",
#         "decision","action","reasons","offer","priority"
#     ]

#     df[final_cols].to_csv(output_file, index=False)

#     print("✅ Prediction completed:", output_file)

#     return df


# if __name__ == "__main__":
#     predict_orders("client_data_shopify.csv", "output.csv")


import os
import pandas as pd
import pickle
import numpy as np

# ================= ABSOLUTE PATHS =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_pkl(filename):
    path = os.path.join(BASE_DIR, filename)
    with open(path, "rb") as f:
        return pickle.load(f)

# ================= LOAD MODELS =================
model       = load_pkl("my_final_rto_prediction_model.pkl")
pincode_map = load_pkl("pincode_risk.pkl")
courier_map = load_pkl("courier_risk.pkl")
city_map    = load_pkl("city_risk.pkl")
device_map  = load_pkl("device_risk.pkl")
channel_map = load_pkl("channel_risk.pkl")
day_map     = load_pkl("day_risk.pkl")

# ================= FIXED THRESHOLDS =================
# Trained on full dataset — stable regardless of batch size
# Adjust these if model accuracy drifts after retraining
HIGH_THRESHOLD   = 0.65
MEDIUM_THRESHOLD = 0.40

# ================= COLUMN MAPPING =================
def smart_column_mapping(df):
    mapping = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        if ("order" in col_lower and ("id" in col_lower or "number" in col_lower)) or col_lower == "id":
            mapping[col] = "order_id"
        elif "amount" in col_lower or "value" in col_lower or "price" in col_lower:
            mapping[col] = "order_value"
        elif "payment" in col_lower or "mode" in col_lower:
            mapping[col] = "payment_type"
        elif "pin" in col_lower or "zip" in col_lower:
            mapping[col] = "pincode"
        elif "hour" in col_lower or "time" in col_lower:
            mapping[col] = "order_hour"
        elif "day" in col_lower and "delivery" not in col_lower:
            mapping[col] = "order_day"
        elif "city" in col_lower:
            mapping[col] = "customer_city"
        elif "state" in col_lower:
            mapping[col] = "state"
        elif "device" in col_lower:
            mapping[col] = "device_type"
        elif "channel" in col_lower:
            mapping[col] = "order_channel"
        elif "previous" in col_lower or "total_orders" in col_lower:
            mapping[col] = "num_previous_orders"
        elif "past_cod" in col_lower or "cod_orders" in col_lower:
            mapping[col] = "past_cod_orders"
        elif "attempt" in col_lower:
            mapping[col] = "payment_attempts"
        elif "delivery" in col_lower:
            mapping[col] = "estimated_delivery_days"
        elif "rto" in col_lower:
            mapping[col] = "past_rto_count"
        elif "courier" in col_lower or "logistics" in col_lower:
            mapping[col] = "courier"
        elif "address" in col_lower:
            mapping[col] = "address_quality"
        elif "category" in col_lower or "product" in col_lower:
            mapping[col] = "product_category"
        elif "phone" in col_lower:
            mapping[col] = "customer_phone"
    return df.rename(columns=mapping)

# ================= ENSURE COLUMNS =================
def ensure_columns(df):
    defaults = {
        "payment_attempts": 1,
        "num_previous_orders": 0,
        "past_rto_count": 0,
        "past_cod_orders": 0,
        "estimated_delivery_days": 5,
        "address_quality": 2,
        "order_hour": 12,
        "order_day": "Mon",
        "courier": "Unknown",
        "device_type": "Mobile",
        "order_channel": "Website",
        "customer_city": "Unknown",
        "payment_type": "COD",  # safe default — assume COD if not specified
    }
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
    return df

# ================= TRANSFORM =================
def transform_columns(df):
    df["address_quality"] = pd.to_numeric(df["address_quality"], errors="coerce").fillna(2)

    # Always create is_cod — safe now because ensure_columns guarantees payment_type exists
    df["is_cod"] = (df["payment_type"].astype(str).str.upper() == "COD").astype(int)

    numeric_cols = [
        "past_cod_orders", "past_rto_count", "order_value",
        "pincode", "payment_attempts", "num_previous_orders",
        "estimated_delivery_days", "order_hour"
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df

# ================= FEATURE ENGINEERING =================
def feature_engineering(df):
    df["is_high_value"]          = (df["order_value"] > 3000).astype(int)
    df["cod_high_value"]         = ((df["is_cod"] == 1) & (df["is_high_value"] == 1)).astype(int)
    df["many_payment_attempts"]  = (df["payment_attempts"] > 2).astype(int)
    df["previous_rto_flag"]      = (df["past_rto_count"] > 0).astype(int)
    df["rto_rate_customer"]      = df["past_rto_count"] / (df["num_previous_orders"] + 1)
    df["is_new_customer"]        = (df["num_previous_orders"] == 0).astype(int)
    return df

# ================= APPLY MAPS =================
def apply_risk_maps(df):
    df["pincode_risk"]        = df["pincode"].map(pincode_map)
    df["courier_performance"] = df["courier"].map(courier_map)
    df["city_risk"]           = df["customer_city"].map(city_map)
    df["device_risk"]         = df["device_type"].map(device_map)
    df["channel_risk"]        = df["order_channel"].map(channel_map)
    df["day_risk"]            = df["order_day"].map(day_map)
    df.fillna(0.5, inplace=True)
    return df

# ================= SANITIZE =================
def sanitize_for_model(df):
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df

# ================= EXPLAINABILITY =================
def generate_reasons(row):
    reasons = []
    if row["past_rto_count"] >= 2:
        reasons.append("High past RTO history")
    if row["pincode_risk"] > 0.7:
        reasons.append("High-risk pincode")
    if row["order_value"] > 1500:
        reasons.append("High order value")
    if row["is_new_customer"] == 1:
        reasons.append("New customer")
    if row["many_payment_attempts"] == 1:
        reasons.append("Multiple payment attempts")
    return ", ".join(reasons) if reasons else "Low risk profile"

# ================= SAVINGS =================
def calculate_savings(df):
    high_df    = df[df["risk_level"] == "HIGH"]
    total_value = high_df["order_value"].sum()
    rto_rate   = 0.6
    prevention = 0.5
    savings    = total_value * rto_rate * prevention
    return round(savings)

# ================= CORE PREDICTION (reusable by both CSV and API routes) =================
def run_prediction_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """
    Takes a raw DataFrame, runs full pipeline, returns results DataFrame.
    Used by both CSV upload route and single order API route.
    """
    df.columns = df.columns.str.lower().str.strip()
    df = smart_column_mapping(df)
    df = df.loc[:, ~df.columns.duplicated()]
    df = ensure_columns(df)
    df = transform_columns(df)
    df = feature_engineering(df)
    df = apply_risk_maps(df)

    features = [
        'is_cod', 'is_new_customer', 'previous_rto_flag',
        'many_payment_attempts', 'cod_high_value',
        'order_value', 'estimated_delivery_days',
        'address_quality', 'rto_rate_customer',
        'pincode_risk', 'courier_performance',
        'city_risk', 'device_risk', 'channel_risk', 'day_risk'
    ]

    X = sanitize_for_model(df[features].copy())

    # ===== PREDICT =====
    probs = model.predict_proba(X)[:, 1]
    df["risk_score"] = probs

    # ===== FIXED THRESHOLDS (stable for 1 or 10,000 orders) =====
    def get_risk(score):
        if score >= HIGH_THRESHOLD:
            return "HIGH"
        elif score >= MEDIUM_THRESHOLD:
            return "MEDIUM"
        else:
            return "LOW"

    df["risk_level"] = df["risk_score"].apply(get_risk)

    # ===== DECISION =====
    def decision(row):
        if row["risk_level"] == "HIGH":
            return "BLOCK_COD"
        elif row["risk_level"] == "MEDIUM":
            return "VERIFY"
        else:
            return "ALLOW"

    df["decision"] = df.apply(decision, axis=1)

    # ===== ACTION =====
    def action(row):
        if row["risk_level"] == "HIGH":
            return "Block COD" if row["order_value"] > 1500 else "Convert to Prepaid"
        elif row["risk_level"] == "MEDIUM":
            return "Call / WhatsApp"
        else:
            return "Proceed"

    df["action"] = df.apply(action, axis=1)

    # ===== OFFERS =====
    df["offer"] = df["risk_level"].map({
        "HIGH":   "10% OFF",
        "MEDIUM": "5% OFF",
        "LOW":    "No"
    })

    df["priority"] = df["risk_level"]
    df["reasons"]  = df.apply(generate_reasons, axis=1)

    return df

# ================= CSV FILE ENTRY POINT =================
def predict_orders(input_file, output_file):
    df      = pd.read_csv(input_file)
    result  = run_prediction_pipeline(df)
    savings = calculate_savings(result)

    print(f"\n💰 Estimated Savings: ₹{savings}")

    final_cols = [
        "order_id", "order_value", "risk_score", "risk_level",
        "decision", "action", "reasons", "offer", "priority"
    ]
    result[final_cols].to_csv(output_file, index=False)
    print("✅ Prediction completed:", output_file)
    return result

if __name__ == "__main__":
    predict_orders("client_data_shopify.csv", "output.csv")