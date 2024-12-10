import os
import json
import uuid
import pandas as pd
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import plotly
import plotly.graph_objs as go
import subprocess
import json
import numpy as np

def convert_numpy_types(obj):
    """
    Recursively convert numpy types in the dictionary to native Python types.
    """
    if isinstance(obj, dict):
        new_obj = {}
        for k, v in obj.items():
            # Convert key if it's a numpy type
            if isinstance(k, np.integer):
                k = int(k)
            elif isinstance(k, np.floating):
                k = float(k)
            elif isinstance(k, np.str_):
                k = str(k)
            # Recursively convert the value
            new_obj[k] = convert_numpy_types(v)
        return new_obj
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.str_):
        return str(obj)
    else:
        return obj


app = Flask(__name__)
app.secret_key = "your_secret_key"

DATA_DIR = "data"
MAIN_DATA_FILE = os.path.join(DATA_DIR, "main_data.xlsx")
SERIES_CONFIG_FILE = os.path.join(DATA_DIR, "series_config.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Initialize files if not present
if not os.path.exists(MAIN_DATA_FILE):
    df_init = pd.DataFrame(columns=["ID","Name","1 Correct","1 Wrong","1 Marks","1 Percentage",
                                    "2 Correct","2 Wrong","2 Marks","2 Percentage",
                                    "3 Correct","3 Wrong","3 Marks","3 Percentage",
                                    "Total Marks in MCQ","Total Percentage","Rank in MCQ",
                                    "Essay 1","Essay 2","Essay 3","Essay 4",
                                    "Total Marks","Rank"])
    df_init.to_excel(MAIN_DATA_FILE, index=False)

if not os.path.exists(SERIES_CONFIG_FILE):
    with open(SERIES_CONFIG_FILE, 'w') as f:
        json.dump({}, f)

def load_series_config():
    with open(SERIES_CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_series_config(cfg):
    with open(SERIES_CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=4)

def load_main_data():
    if os.path.exists(MAIN_DATA_FILE):
        return pd.read_excel(MAIN_DATA_FILE)
    else:
        return pd.DataFrame()

def save_main_data(df):
    df.to_excel(MAIN_DATA_FILE, index=False)

def clean_data(df):
    # Remove rows where ID and Name are both empty
    df = df[~(df["ID"].isna() & df["Name"].isna())]
    return df

def recompute_ranks(df, series_id, test_id):
    # Recompute ranks based on Total Marks (overall)
    df_test = df[(df["SeriesID"] == series_id) & (df["TestID"] == test_id)].copy()
    df_test = df_test[~(df_test["ID"].isna()) & ~(df_test["Name"].isna())]
    df_test = df_test.sort_values("Total Marks", ascending=False)
    df_test["Rank"] = range(1, len(df_test) + 1)
    for i, row in df_test.iterrows():
        df.loc[i, "Rank"] = row["Rank"]
    return df

def compute_class_metrics(df_test):
    # Compute class average accuracy and attempts per section
    metrics = {}
    for sec_id in ["1","2","3"]:
        correct_col = f"{sec_id} Correct"
        wrong_col = f"{sec_id} Wrong"
        if correct_col in df_test.columns and wrong_col in df_test.columns:
            total_correct = df_test[correct_col].sum()
            attempts = df_test[correct_col] + df_test[wrong_col]
            total_attempts = attempts.sum()
            if total_attempts > 0:
                class_accuracy = (total_correct / total_attempts)*100
                class_attempts = attempts.mean()
            else:
                class_accuracy = 0.0
                class_attempts = 0.0
        else:
            class_accuracy = 0.0
            class_attempts = 0.0
        metrics[sec_id] = {
            "class_accuracy": class_accuracy,
            "class_attempts": class_attempts
        }
    return metrics

def section_analysis(row, sec_map, class_metrics):
    sections = []
    for sec_id in ["1","2","3"]:
        correct = row.get(f"{sec_id} Correct",0)
        wrong = row.get(f"{sec_id} Wrong",0)
        attempted = correct + wrong
        if attempted > 0:
            accuracy = round((correct/attempted)*100,2)
        else:
            accuracy = 0.0
        diff_acc = round(accuracy - class_metrics[sec_id]["class_accuracy"],2)
        diff_attempts = round(attempted - class_metrics[sec_id]["class_attempts"],2)

        sections.append({
            "sec_id": sec_id,
            "name": sec_map.get(sec_id, f"Section {sec_id}"),
            "correct": correct,
            "wrong": wrong,
            "attempted": attempted,
            "accuracy": accuracy,
            "diff_vs_class_acc": diff_acc,
            "diff_vs_class_attempts": diff_attempts
        })
    return sections

def generate_student_analysis_text(name, rank, total_marks, gap_from_top5, sections):
    # Generate detailed textual analysis similar to sample
    text = f"{name} (Rank {rank}, Total Marks: {total_marks})\n\n"
    gap_str = f"{'+' if gap_from_top5>=0 else ''}{gap_from_top5}"
    text += f"Gap from Top 5: {gap_str} marks\n\nSection-wise Analysis:\n"
    for sec in sections:
        # e.g. Section 1: 95.24% accuracy (+14.16% vs class), +1.93 more questions attempted
        att_comp = f"{('+' if sec['diff_vs_class_attempts']>=0 else '')}{sec['diff_vs_class_attempts']}"
        if att_comp == '+0.0':
            att_comp = "similar attempt rate"
        else:
            att_comp += " more questions attempted" if sec['diff_vs_class_attempts']>=0 else " less questions attempted"

        text += f"\n{sec['name']}: {sec['accuracy']}% accuracy ({('+' if sec['diff_vs_class_acc']>=0 else '')}{sec['diff_vs_class_acc']}% vs class), {att_comp}"

    # Add a simple strategy suggestion based on gap_from_top5
    text += "\n\n"
    if rank == 1:
        text += "Strengths: Top performer!\nStrategy: Keep up the good work.\n"
    elif gap_from_top5 < 0:
        text += "Needs Improvement: Falling behind top performers.\nStrategy: Increase accuracy and attempt rate in weaker sections.\n"
    else:
        text += "Good performance, but room for improvement.\nFocus on weaker sections to close the gap.\n"

    return text

def generate_test_analysis(df, series_id, test_id, row, sections):
    # Generate analysis for a single student's test performance
    df_test = df[(df["SeriesID"]==series_id) & (df["TestID"]==test_id)]
    df_test = df_test[~df_test["ID"].isna() & ~df_test["Name"].isna()]
    if len(df_test)==0:
        return "No data for this test.", {}

    # top 5 avg
    df_test_sorted = df_test.sort_values("Total Marks", ascending=False)
    top5 = df_test_sorted.head(5)
    top5_avg = top5["Total Marks"].mean()

    total_marks = row["Total Marks"]
    rank = row["Rank"]
    if pd.isna(total_marks):
        total_marks = 0
    gap_from_top5 = round(total_marks - top5_avg,2)

    class_metrics = compute_class_metrics(df_test)
    stu_sections = section_analysis(row, sections, class_metrics)
    analysis = generate_student_analysis_text(row["Name"], rank, total_marks, gap_from_top5, stu_sections)
    return analysis, class_metrics

def generate_series_trends(df_student):
    # For a single student in a series, generate marks and rank trend arrays
    df_student = df_student.sort_values("TestName")
    test_names = df_student["TestName"].tolist()
    marks_trend = df_student["Total Marks"].fillna(0).tolist()
    rank_trend = df_student["Rank"].tolist()
    return test_names, marks_trend, rank_trend

@app.route("/")
def home():
    cfg = load_series_config()
    series_list = []
    for sid, sdata in cfg.items():
        series_list.append({
            "id": sid,
            "name": sdata.get("series_name", "Unnamed Series"),
            "tests": sdata.get("tests", {})
        })
    return render_template("home.html", series_list=series_list, title="Home")

@app.route("/create_series", methods=["GET", "POST"])
def create_series():
    if request.method == "POST":
        series_name = request.form.get("series_name")
        sec1 = request.form.get("sec1_name", "Section 1")
        sec2 = request.form.get("sec2_name", "Section 2")
        sec3 = request.form.get("sec3_name", "Section 3")
        essays_included = request.form.get("essays_included") == "on"

        sid = str(uuid.uuid4())
        cfg = load_series_config()
        cfg[sid] = {
            "series_name": series_name,
            "sections": {
                "1": sec1,
                "2": sec2,
                "3": sec3
            },
            "essays_included": essays_included,
            "tests": {}
        }
        save_series_config(cfg)
        flash("Series created successfully", "success")
        return redirect(url_for('home'))
    return render_template("create_series.html", title="Create Series")

@app.route("/series/<series_id>")
def view_series(series_id):
    df = load_main_data()
    df = clean_data(df)
    cfg = load_series_config()
    if series_id not in cfg:
        flash("Series not found", "danger")
        return redirect(url_for('home'))
    series_data = cfg[series_id]
    tests = series_data.get("tests", {})

    graphJSON = None
    if tests:
        df_series = df[df["SeriesID"] == series_id]
        test_ids = []
        avg_marks = []
        for tid, tname in tests.items():
            df_test = df_series[df_series["TestID"] == tid]
            df_test = df_test[~df_test["ID"].isna() & ~df_test["Name"].isna()]
            if len(df_test) > 0:
                test_ids.append(tname)
                avg_marks.append(df_test["Total Marks"].mean())
        if test_ids:
            fig = go.Figure([go.Scatter(x=test_ids, y=avg_marks, mode='lines+markers', name='Average Marks')])
            fig.update_layout(title="Average Marks Trend", xaxis_title="Test", yaxis_title="Average Marks")
            graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template("series.html", series=series_data, series_id=series_id, graphJSON=graphJSON, title=series_data.get("series_name","Series"))

@app.route("/series/<series_id>/add_test", methods=["GET", "POST"])
def add_test(series_id):
    cfg = load_series_config()
    if series_id not in cfg:
        flash("Series not found", "danger")
        return redirect(url_for('home'))

    essays_included = cfg[series_id].get("essays_included", False)

    if request.method == "POST":
        test_name = request.form.get("test_name")
        f = request.files.get("excel_file")

        upload_df = pd.read_excel(f)

        # Required MCQ columns
        mcq_cols = ["ID","Name","1 Correct","1 Wrong","1 Marks","1 Percentage",
                    "2 Correct","2 Wrong","2 Marks","2 Percentage",
                    "3 Correct","3 Wrong","3 Marks","3 Percentage",
                    "Total Marks in MCQ","Total Percentage","Rank in MCQ",
                    "Total Marks","Rank"]
        # Essay columns if essays_included
        essay_cols = ["Essay 1","Essay 2","Essay 3","Essay 4"] if essays_included else []

        for col in mcq_cols:
            if col not in upload_df.columns:
                upload_df[col] = np.nan
        for col in essay_cols:
            if col not in upload_df.columns:
                upload_df[col] = np.nan

        upload_df = clean_data(upload_df)
        tid = str(uuid.uuid4())
        upload_df["SeriesID"] = series_id
        upload_df["TestID"] = tid
        upload_df["TestName"] = test_name

        main_df = load_main_data()
        main_df = pd.concat([main_df, upload_df], ignore_index=True)
        main_df = recompute_ranks(main_df, series_id, tid)

        save_main_data(main_df)
        cfg[series_id]["tests"][tid] = test_name
        save_series_config(cfg)
        flash("Test added successfully", "success")
        return redirect(url_for('view_series', series_id=series_id))

    return render_template("upload.html", title="Add Test", essays_included=essays_included)

@app.route("/delete_series/<series_id>", methods=["POST"])
def delete_series(series_id):
    cfg = load_series_config()
    if series_id not in cfg:
        flash("Series not found", "danger")
        return redirect(url_for('home'))
    df = load_main_data()
    df = df[df["SeriesID"] != series_id]
    save_main_data(df)

    del cfg[series_id]
    save_series_config(cfg)
    flash("Series deleted successfully", "success")
    return redirect(url_for('home'))

@app.route("/delete_test/<series_id>/<test_id>", methods=["POST"])
def delete_test(series_id, test_id):
    cfg = load_series_config()
    if series_id not in cfg or test_id not in cfg[series_id]["tests"]:
        flash("Test not found", "danger")
        return redirect(url_for('home'))
    df = load_main_data()
    df = df[~((df["SeriesID"] == series_id) & (df["TestID"] == test_id))]
    save_main_data(df)

    del cfg[series_id]["tests"][test_id]
    save_series_config(cfg)
    flash("Test deleted successfully", "success")
    return redirect(url_for('view_series', series_id=series_id))

@app.route("/series/<series_id>/test/<test_id>")
def view_test(series_id, test_id):
    cfg = load_series_config()
    if series_id not in cfg or test_id not in cfg[series_id]["tests"]:
        flash("Test not found", "danger")
        return redirect(url_for('home'))

    test_name = cfg[series_id]["tests"][test_id]
    df = load_main_data()
    df = clean_data(df)
    df_test = df[(df["SeriesID"]==series_id) & (df["TestID"]==test_id)]
    if len(df_test)==0:
        flash("No data for this test", "info")
        return redirect(url_for('view_series', series_id=series_id))

    essays_included = cfg[series_id].get("essays_included",False)
    # Sort by rank to display
    df_test = df_test.sort_values("Rank", ascending=True, na_position='last')
    students = df_test.to_dict(orient="records")

    # Optional: You can generate analysis text for each student here if desired. 
    # But currently test.html just shows raw data. The analysis is mainly done in export or in the single student page.

    return render_template("test.html", test_name=test_name, students=students, essays_included=essays_included, title=test_name)

@app.route("/series/<series_id>/student/<student_id>")
def view_student(series_id, student_id):
    cfg = load_series_config()
    if series_id not in cfg:
        flash("Series not found","danger")
        return redirect(url_for('home'))

    df = load_main_data()
    df = clean_data(df)
    df_student = df[(df["SeriesID"] == series_id) & (df["ID"] == float(student_id))]

    if len(df_student)==0:
        flash("Student not found in this series","info")
        return redirect(url_for('view_series', series_id=series_id))
    student_name = df_student["Name"].iloc[0]

    test_names, marks_trend, rank_trend = generate_series_trends(df_student)

    fig_marks = go.Figure([go.Scatter(x=test_names, y=marks_trend, mode='lines+markers', name='Marks')])
    fig_marks.update_layout(title=f"{student_name}'s Marks Trend", xaxis_title="Test", yaxis_title="Marks")
    marks_graphJSON = json.dumps(fig_marks, cls=plotly.utils.PlotlyJSONEncoder)

    fig_rank = go.Figure([go.Scatter(x=test_names, y=rank_trend, mode='lines+markers', name='Rank', line=dict(color='red'))])
    fig_rank.update_layout(title=f"{student_name}'s Rank Trend", xaxis_title="Test", yaxis_title="Rank", yaxis=dict(autorange="reversed"))
    rank_graphJSON = json.dumps(fig_rank, cls=plotly.utils.PlotlyJSONEncoder)

    # Show last test details
    last_test = df_student.iloc[-1]
    essays_included = cfg[series_id].get("essays_included", False)
    sec_map = cfg[series_id]["sections"]

    return render_template("student.html", student_name=student_name,
                           marks_graphJSON=marks_graphJSON,
                           rank_graphJSON=rank_graphJSON,
                           last_test=last_test,
                           sections=sec_map,
                           essays_included=essays_included,
                           title=student_name)

@app.route("/export")
def export_site():
    df = load_main_data()
    df = clean_data(df)
    cfg = load_series_config()

    # Build data for single-page export
    students_data = {}
    for sid, sdata in cfg.items():
        series_tests = sdata.get("tests", {})
        df_series = df[df["SeriesID"] == sid]

        for student_id in df_series["ID"].unique():
            df_stu = df_series[df_series["ID"] == student_id]
            if len(df_stu) == 0:
                continue
            student_name = df_stu["Name"].iloc[0]

            # Convert student_id to str to ensure it's JSON-serializable
            student_id_str = str(student_id)

            if student_id_str not in students_data:
                students_data[student_id_str] = {
                    "name": student_name,
                    "series": {}
                }
            if sid not in students_data[student_id_str]["series"]:
                students_data[student_id_str]["series"][sid] = {
                    "series_name": sdata["series_name"],
                    "sections": sdata["sections"],
                    "essays_included": sdata.get("essays_included", False),
                    "tests": {},
                    "marks_trend": [],
                    "rank_trend": [],
                    "test_names": []
                }

            for tid, tname in series_tests.items():
                df_test = df_stu[df_stu["TestID"] == tid]
                if len(df_test) == 0:
                    # Absent
                    students_data[student_id_str]["series"][sid]["tests"][tid] = {
                        "test_name": tname,
                        "student_data": {"Absent": True}
                    }
                else:
                    row = df_test.iloc[0].to_dict()
                    # Add to trend
                    tm = row.get("Total Marks", 0)
                    rk = row.get("Rank", None)
                    if pd.isna(tm):
                        tm = 0
                    series_data = students_data[student_id_str]["series"][sid]
                    series_data["marks_trend"].append(tm)
                    series_data["rank_trend"].append(rk)
                    series_data["test_names"].append(tname)

                    # Generate analysis
                    analysis, class_metrics = generate_test_analysis(df, sid, tid, row, sdata["sections"])
                    # Improvement indicators
                    df_stu_sorted = df_stu.sort_values("TestName")
                    prev_tests = df_stu_sorted[df_stu_sorted["TestName"] < tname]
                    improvement = {"marks": "", "rank": ""}
                    if len(prev_tests) > 0:
                        prev_test = prev_tests.iloc[-1]
                        if prev_test["Total Marks"] < row["Total Marks"]:
                            improvement["marks"] = "↑"
                        elif prev_test["Total Marks"] > row["Total Marks"]:
                            improvement["marks"] = "↓"
                        else:
                            improvement["marks"] = "→"

                        if prev_test["Rank"] > row["Rank"]:
                            improvement["rank"] = "↑"
                        elif prev_test["Rank"] < row["Rank"]:
                            improvement["rank"] = "↓"
                        else:
                            improvement["rank"] = "→"
                    else:
                        # First test in the series for this student, no previous comparison
                        improvement = {"marks": "N/A", "rank": "N/A"}

                    students_data[student_id_str]["series"][sid]["tests"][tid] = {
                        "test_name": tname,
                        "student_data": row,
                        "analysis": analysis,
                        "class_metrics": class_metrics,
                        "improvement": improvement
                    }

    # Convert all numpy types in students_data to native Python types
    students_data_clean = convert_numpy_types(students_data)

    build_dir = "build"
    if not os.path.exists(build_dir):
        os.makedirs(build_dir)

    with app.test_request_context('/'):
        html = render_template("export_single_page.html", 
                               students_data=json.dumps(students_data_clean),
                               title="Consolidated Analysis")
        with open(os.path.join(build_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

    flash("Export completed. The 'build/index.html' is ready. Push it to GitHub Pages.", "success")
    return redirect(url_for('home'))

@app.route("/preview_github")
def preview_github():
    return send_from_directory("build","index.html")

@app.route("/push_to_github", methods=["POST"])
def push_to_github():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Update"], check=True)
        subprocess.run(["git", "push"], check=True)
        flash("GitHub update completed successfully.", "success")
    except subprocess.CalledProcessError as e:
        flash("Failed to push to GitHub. Ensure git is set up correctly. Error: "+str(e), "danger")
    return redirect(url_for('home'))

if __name__ == "__main__":
    # Run the app
    app.run(debug=True, port=5001)
