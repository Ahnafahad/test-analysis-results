import os
import json
import uuid
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash
import plotly
import plotly.graph_objs as go

app = Flask(__name__)
app.secret_key = "your_secret_key"

DATA_DIR = "data"
MAIN_DATA_FILE = os.path.join(DATA_DIR, "main_data.xlsx")
SERIES_CONFIG_FILE = os.path.join(DATA_DIR, "series_config.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Initialize main_data and series_config if not present
if not os.path.exists(MAIN_DATA_FILE):
    df_init = pd.DataFrame(columns=["ID","Name","SeriesID","TestID","TestName",
                                    "1 Correct","1 Wrong","1 Marks","1 Percentage",
                                    "2 Correct","2 Wrong","2 Marks","2 Percentage",
                                    "3 Correct","3 Wrong","3 Marks","3 Percentage",
                                    "Total Marks","Total Percentage","Rank","Total Question","Penalty"])
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
    return pd.read_excel(MAIN_DATA_FILE)

def save_main_data(df):
    df.to_excel(MAIN_DATA_FILE, index=False)

def recompute_ranks(df, series_id, test_id):
    df_test = df[(df["SeriesID"] == series_id) & (df["TestID"] == test_id)].copy()
    df_test = df_test.sort_values("Total Marks", ascending=False)
    df_test["Rank"] = range(1, len(df_test) + 1)
    # Update ranks back into main df
    for i, row in df_test.iterrows():
        df.loc[i, "Rank"] = row["Rank"]
    return df

@app.route("/")
def home():
    # Show all series
    cfg = load_series_config()
    series_list = []
    for sid, sdata in cfg.items():
        series_list.append({
            "id": sid,
            "name": sdata.get("series_name", "Unnamed Series"),
            "tests": sdata.get("tests", {})
        })
    return render_template("home.html", series_list=series_list)

@app.route("/create_series", methods=["GET", "POST"])
def create_series():
    if request.method == "POST":
        series_name = request.form.get("series_name")
        sid = str(uuid.uuid4())
        cfg = load_series_config()
        cfg[sid] = {
            "series_name": series_name,
            "sections": {},
            "tests": {}
        }
        save_series_config(cfg)
        flash("Series created successfully", "success")
        return redirect(url_for('home'))
    return render_template("create_series.html")

@app.route("/series/<series_id>")
def view_series(series_id):
    df = load_main_data()
    cfg = load_series_config()
    if series_id not in cfg:
        flash("Series not found", "danger")
        return redirect(url_for('home'))
    series_data = cfg[series_id]
    tests = series_data.get("tests", {})

    # Create a performance trend graph for average marks across tests (if tests exist)
    graphJSON = None
    if tests:
        df_series = df[df["SeriesID"] == series_id]
        test_ids = []
        avg_marks = []
        for tid, tname in tests.items():
            df_test = df_series[df_series["TestID"] == tid]
            if len(df_test) > 0:
                test_ids.append(tname)
                avg_marks.append(df_test["Total Marks"].mean())
        if test_ids:
            fig = go.Figure([go.Scatter(x=test_ids, y=avg_marks, mode='lines+markers', name='Average Marks')])
            fig.update_layout(title="Average Marks Trend", xaxis_title="Test", yaxis_title="Average Marks")
            graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template("series.html", series=series_data, series_id=series_id, graphJSON=graphJSON)

@app.route("/series/<series_id>/add_test", methods=["GET", "POST"])
def add_test(series_id):
    cfg = load_series_config()
    if series_id not in cfg:
        flash("Series not found", "danger")
        return redirect(url_for('home'))

    if request.method == "POST":
        test_name = request.form.get("test_name")
        f = request.files.get("excel_file")
        sec1 = request.form.get("sec1_name", "Section 1")
        sec2 = request.form.get("sec2_name", "Section 2")
        sec3 = request.form.get("sec3_name", "Section 3")

        # Update section names in config
        cfg[series_id]["sections"]["1"] = sec1
        cfg[series_id]["sections"]["2"] = sec2
        cfg[series_id]["sections"]["3"] = sec3

        upload_df = pd.read_excel(f)
        # Ensure required columns exist in upload
        required_cols = ["ID","Name","1 Correct","1 Wrong","1 Marks","1 Percentage",
                          "2 Correct","2 Wrong","2 Marks","2 Percentage",
                          "3 Correct","3 Wrong","3 Marks","3 Percentage",
                          "Total Marks","Total Percentage","Rank","Total Question","Penalty"]
        for col in required_cols:
            if col not in upload_df.columns:
                # If rank not computed in given excel, we will compute after. It's okay if not present initially
                if col == "Rank":
                    continue
                if col == "Penalty":
                    upload_df["Penalty"] = 0
                    continue
                # If something else is missing
                if col not in upload_df.columns:
                    # Fill missing with 0 if marks/wrong/correct not present
                    if "Correct" in col or "Wrong" in col or "Marks" in col or "Percentage" in col or "Total" in col:
                        upload_df[col] = 0
                    else:
                        upload_df[col] = ""
        
        tid = str(uuid.uuid4())
        upload_df["SeriesID"] = series_id
        upload_df["TestID"] = tid
        upload_df["TestName"] = test_name

        main_df = load_main_data()
        main_df = pd.concat([main_df, upload_df], ignore_index=True)
        # Compute ranks
        main_df = recompute_ranks(main_df, series_id, tid)

        save_main_data(main_df)
        cfg[series_id]["tests"][tid] = test_name
        save_series_config(cfg)
        flash("Test added successfully", "success")
        return redirect(url_for('view_series', series_id=series_id))

    return render_template("upload.html")

@app.route("/delete_series/<series_id>", methods=["POST"])
def delete_series(series_id):
    cfg = load_series_config()
    if series_id not in cfg:
        flash("Series not found", "danger")
        return redirect(url_for('home'))
    # Remove all tests from main_data
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
    # Remove test from main_data
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
    sec_map = cfg[series_id].get("sections", {"1": "Section 1", "2": "Section 2", "3": "Section 3"})

    df = load_main_data()
    df_test = df[(df["SeriesID"] == series_id) & (df["TestID"] == test_id)].copy()
    if len(df_test) == 0:
        flash("No data for this test", "info")
        return redirect(url_for('view_series', series_id=series_id))

    # Compute top 5 average
    df_test = df_test.sort_values("Total Marks", ascending=False)
    top5 = df_test.head(5)
    top5_avg = top5["Total Marks"].mean()

    # Compute class metrics for accuracy and attempts per section
    class_metrics = compute_class_metrics(df_test)

    # Prepare detailed analysis for each student
    students_analysis = []
    for i, row in df_test.iterrows():
        student_id = row["ID"]
        student_name = row["Name"]
        total_marks = row["Total Marks"]
        rank = int(row["Rank"])
        gap_from_top5 = round(total_marks - top5_avg, 2)

        # Section-wise analysis
        student_sections = section_analysis(row, sec_map)
        for sec in student_sections:
            sec_id = sec["sec_id"]
            sec["diff_vs_class_acc"] = round(sec["accuracy"] - class_metrics[sec_id]["class_accuracy"], 2)
            sec["diff_vs_class_attempts"] = round(sec["attempted"] - class_metrics[sec_id]["class_attempts"], 2)

        # Determine category (top performer, middle, lower)
        category = "Top Performer" if rank <=5 else "Middle" if rank<=10 else "Lower"

        # Generate textual analysis similar to sample
        # We'll produce a short description based on category
        analysis_text = generate_student_analysis_text(student_name, rank, total_marks, gap_from_top5, student_sections, category)

        students_analysis.append({
            "ID": student_id,
            "Name": student_name,
            "Rank": rank,
            "TotalMarks": total_marks,
            "GapFromTop5": gap_from_top5,
            "Sections": student_sections,
            "AnalysisText": analysis_text
        })

    # Sort by rank for display
    students_analysis = sorted(students_analysis, key=lambda x: x["Rank"])

    return render_template("test.html", test_name=test_name, students=students_analysis, sections=sec_map)

def compute_class_metrics(df_test):
    # Compute class average accuracy and attempts per section
    metrics = {}
    for sec_id in ["1","2","3"]:
        correct_col = f"{sec_id} Correct"
        wrong_col = f"{sec_id} Wrong"
        if correct_col in df_test.columns and wrong_col in df_test.columns:
            total_correct = df_test[correct_col].sum()
            attempts = (df_test[correct_col] + df_test[wrong_col])
            total_attempts = attempts.sum()
            if total_attempts > 0:
                class_accuracy = (total_correct / total_attempts) * 100
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

def section_analysis(row, sec_map):
    sections = []
    for sec_id in ["1","2","3"]:
        correct = row.get(f"{sec_id} Correct",0)
        wrong = row.get(f"{sec_id} Wrong",0)
        attempted = correct + wrong
        accuracy = round((correct/attempted)*100,2) if attempted>0 else 0.0
        sections.append({
            "sec_id": sec_id,
            "name": sec_map.get(sec_id, f"Section {sec_id}"),
            "correct": correct,
            "wrong": wrong,
            "attempted": attempted,
            "accuracy": accuracy
        })
    return sections

def generate_student_analysis_text(name, rank, total_marks, gap_from_top5, sections, category):
    # Generate a textual summary like the sample provided
    # We'll produce a summary mentioning rank, total marks, gap from top5,
    # and a brief section-wise comment.
    text = f"{name} (Rank {rank}, Total Marks: {total_marks})\n\n"
    text += f"Gap from Top 5: {('+' if gap_from_top5>=0 else '')}{gap_from_top5} marks\n"

    text += "Section-wise Analysis:\n"
    for sec in sections:
        text += f"\n{sec['name']}: {sec['accuracy']}% accuracy "
        diff_acc = sec['diff_vs_class_acc']
        diff_attempt = sec['diff_vs_class_attempts']
        text += f"({('+' if diff_acc>=0 else '')}{diff_acc}% vs class), "
        text += f"{('+' if diff_attempt>=0 else '')}{diff_attempt} questions attempted vs class\n"

    # Determine strengths or suggestions based on category
    if category == "Top Performer":
        text += "\nStrengths: High performer across sections.\n"
        text += "Strategy: Maintain accuracy and attempt rate."
    elif category == "Middle":
        text += "\nPotential: Improve attempt rate or accuracy in weaker sections.\n"
        text += "Strategy: Identify weaker sections and focus on them."
    else:
        text += "\nNeeds Improvement: Falling behind class averages.\n"
        text += "Strategy: Revise fundamentals and attempt more questions accurately."

    return text

@app.route("/series/<series_id>/student/<student_id>")
def view_student(series_id, student_id):
    cfg = load_series_config()
    if series_id not in cfg:
        flash("Series not found", "danger")
        return redirect(url_for('home'))

    df = load_main_data()
    df_student = df[(df["SeriesID"] == series_id) & (df["ID"] == int(student_id))]
    if len(df_student) == 0:
        flash("Student not found in this series", "info")
        return redirect(url_for('view_series', series_id=series_id))
    student_name = df_student["Name"].iloc[0]

    # Sort tests by TestName (assuming alphabetical or chronological naming)
    df_student = df_student.sort_values("TestName")

    test_names = df_student["TestName"].tolist()
    marks_trend = df_student["Total Marks"].tolist()
    rank_trend = df_student["Rank"].tolist()

    # Marks trend graph
    fig_marks = go.Figure([go.Scatter(x=test_names, y=marks_trend, mode='lines+markers', name='Marks')])
    fig_marks.update_layout(title=f"{student_name}'s Marks Trend", xaxis_title="Test", yaxis_title="Marks")
    marks_graphJSON = json.dumps(fig_marks, cls=plotly.utils.PlotlyJSONEncoder)

    # Rank trend graph (lower rank = better, so invert y-axis)
    fig_rank = go.Figure([go.Scatter(x=test_names, y=rank_trend, mode='lines+markers', name='Rank', line=dict(color='red'))])
    fig_rank.update_layout(title=f"{student_name}'s Rank Trend", xaxis_title="Test", yaxis_title="Rank", yaxis=dict(autorange="reversed"))
    rank_graphJSON = json.dumps(fig_rank, cls=plotly.utils.PlotlyJSONEncoder)

    last_test = df_student.iloc[-1]
    series_sec_map = cfg[series_id].get("sections", {"1": "Section 1", "2": "Section 2", "3": "Section 3"})
    last_test_sections = section_analysis(last_test, series_sec_map)

    improvement = {}
    if len(df_student) > 1:
        prev_test = df_student.iloc[-2]
        improvement["marks"] = "↑" if last_test["Total Marks"] > prev_test["Total Marks"] else "↓"
        # For rank, a lower number is better, so if last_test < prev_test => improvement "↑"
        improvement["rank"] = "↑" if last_test["Rank"] < prev_test["Rank"] else "↓"
    else:
        improvement["marks"] = ""
        improvement["rank"] = ""

    return render_template("student.html", student_name=student_name,
                           marks_graphJSON=marks_graphJSON,
                           rank_graphJSON=rank_graphJSON,
                           last_test=last_test,
                           sections=last_test_sections,
                           improvement=improvement)

@app.route("/export")
def export_site():
    # Render all pages statically into build directory
    cfg = load_series_config()
    df = load_main_data()

    build_dir = "build"
    if not os.path.exists(build_dir):
        os.makedirs(build_dir)

    # Home
    with app.test_request_context('/'):
        html = home()
        with open(os.path.join(build_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

    # Export each series and its tests and students
    for sid, sdata in cfg.items():
        os.makedirs(os.path.join(build_dir, sid), exist_ok=True)
        with app.test_request_context(f'/series/{sid}'):
            html = view_series(sid)
            with open(os.path.join(build_dir, sid, "index.html"), "w", encoding="utf-8") as f:
                f.write(html)

        for tid, tname in sdata["tests"].items():
            os.makedirs(os.path.join(build_dir, sid, tid), exist_ok=True)
            with app.test_request_context(f'/series/{sid}/test/{tid}'):
                html = view_test(sid, tid)
                with open(os.path.join(build_dir, sid, tid, "index.html"), "w", encoding="utf-8") as f:
                    f.write(html)
            df_test = df[(df["SeriesID"] == sid) & (df["TestID"] == tid)]
            for student_id in df_test["ID"].unique():
                os.makedirs(os.path.join(build_dir, sid, "student_"+str(student_id)), exist_ok=True)
                with app.test_request_context(f'/series/{sid}/student/{student_id}'):
                    html = view_student(sid, student_id)
                    with open(os.path.join(build_dir, sid, "student_"+str(student_id), "index.html"), "w", encoding="utf-8") as f:
                        f.write(html)

    flash("Export completed. Push the 'build' directory to GitHub Pages.", "success")
    return redirect(url_for('home'))


if __name__ == "__main__":
    app.run(debug=True, port=5001)
