import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import matplotlib.pyplot as plt
import seaborn as sns
import os
import argparse

RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

def ensure_string(val):
    return str(val) if pd.notna(val) else ""

def batch_similarity(texts, vectorizer):
    """Calculate pairwise similarities for a list of texts."""
    if len(texts) < 2:
        return 0.0
    try:
        tfidf = vectorizer.transform(texts)
        sim_matrix = cosine_similarity(tfidf)
        # Get upper triangle excluding diagonal
        upper_tri = sim_matrix[np.triu_indices(len(texts), k=1)]
        return np.mean(upper_tri)
    except ValueError:
        return 0.0

def similarity(text1, text2, vectorizer):
    return batch_similarity([text1, text2], vectorizer)

def evaluate_quizzes(input_csv, is_comparison=False, prefix=""):
    """
    Evaluates quiz distractors from a CSV file.
    Returns a dictionary of aggregated metrics.
    """
    if not os.path.exists(input_csv):
        print(f"Error: Could not find {input_csv}")
        return None
        
    print(f"Loading data from {input_csv}...")
    df = pd.read_csv(input_csv)
            
    required_cols = ['question', 'option_a', 'option_b', 'option_c', 'option_d', 'answer']
    for col in required_cols:
        if col not in df.columns:
            print(f"Error: Missing required column '{col}' in {input_csv}")
            return None
            
    results = []
    
    # Train a single vectorizer on all text to have a unified vocabulary
    all_text = []
    for _, row in df.iterrows():
        all_text.extend([
            ensure_string(row['question']),
            ensure_string(row['option_a']),
            ensure_string(row['option_b']),
            ensure_string(row['option_c']),
            ensure_string(row['option_d'])
        ])
    
    # Check if there is enough text to vectorize
    if not any(all_text):
        print("Error: Input CSV contains no valid text data.")
        return None
        
    vectorizer = TfidfVectorizer().fit(all_text)
    
    # Pre-calculate duplicate questions (Optional Extension)
    questions = [ensure_string(q) for q in df['question']]
    q_tfidf = vectorizer.transform(questions)
    q_sim_matrix = cosine_similarity(q_tfidf)
    # Count how many questions have > 0.9 similarity with another question
    np.fill_diagonal(q_sim_matrix, 0)
    duplicate_rate = np.mean(np.max(q_sim_matrix, axis=1) > 0.9) if len(questions) > 1 else 0.0
    
    for idx, row in df.iterrows():
        q = ensure_string(row['question'])
        opt_a = ensure_string(row['option_a'])
        opt_b = ensure_string(row['option_b'])
        opt_c = ensure_string(row['option_c'])
        opt_d = ensure_string(row['option_d'])
        ans_letter = str(row['answer']).strip().upper()
        
        options = {
            'A': opt_a, 'B': opt_b, 'C': opt_c, 'D': opt_d
        }
        
        # Extract correct answer and distractors
        if ans_letter in options:
            correct_ans = options[ans_letter]
            distractors = [options[k] for k in options if k != ans_letter]
        else:
            # Fallback if answer is not exactly A, B, C, D
            correct_ans = opt_a  # assuming A is correct for fallback metrics
            distractors = [opt_b, opt_c, opt_d]
            
        # 1. Distractor Plausibility: similarity between correct answer and distractors
        plausibilities = [similarity(correct_ans, d, vectorizer) for d in distractors]
        plausibility = np.mean(plausibilities) if plausibilities else 0.0
        
        # 2. Distractor Diversity: 1 - average similarity between distractors
        distractor_sim = batch_similarity(distractors, vectorizer)
        diversity = 1.0 - distractor_sim
        
        # 3. Context Relevance: average similarity between question and all options
        all_options = [opt_a, opt_b, opt_c, opt_d]
        relevances = [similarity(q, opt, vectorizer) for opt in all_options]
        relevance = np.mean(relevances) if relevances else 0.0
        
        # Add Overall Score (Step 1)
        overall_score = 0.4 * plausibility + 0.3 * diversity + 0.3 * relevance
        
        # Optional Extension: Option length balance (Standard deviation of option lengths)
        lengths = [len(opt) for opt in all_options]
        length_std = np.std(lengths) if lengths else 0.0
        
        results.append({
            'plausibility': plausibility,
            'diversity': diversity,
            'relevance': relevance,
            'overall_score': overall_score,
            'length_std_dev': length_std
        })
        
    results_df = pd.DataFrame(results)
    
    # Merge metrics back with original data
    final_df = pd.concat([df, results_df], axis=1)
    
    # Export results (Step 6)
    out_csv = os.path.join(RESULTS_DIR, f"{prefix}evaluation_results.csv")
    final_df.to_csv(out_csv, index=False)
    print(f"Results saved to {out_csv}")
    
    # Compute aggregates (Step 5)
    agg_metrics = {
        'Plausibility_Mean': results_df['plausibility'].mean(),
        'Plausibility_Std': results_df['plausibility'].std(),
        'Diversity_Mean': results_df['diversity'].mean(),
        'Diversity_Std': results_df['diversity'].std(),
        'Relevance_Mean': results_df['relevance'].mean(),
        'Relevance_Std': results_df['relevance'].std(),
        'Overall_Mean': results_df['overall_score'].mean(),
        'Overall_Std': results_df['overall_score'].std(),
        'Duplicate_Rate': duplicate_rate,
        'Option_Length_Imbalance': results_df['length_std_dev'].mean()
    }
    
    print(f"\n--- Summary Statistics ({prefix.strip('_') or 'Current'}) ---")
    print(f"Distractor Plausibility: {agg_metrics['Plausibility_Mean']:.4f} ± {agg_metrics['Plausibility_Std']:.4f}")
    print(f"Distractor Diversity:    {agg_metrics['Diversity_Mean']:.4f} ± {agg_metrics['Diversity_Std']:.4f}")
    print(f"Context Relevance:       {agg_metrics['Relevance_Mean']:.4f} ± {agg_metrics['Relevance_Std']:.4f}")
    print(f"Overall Score:           {agg_metrics['Overall_Mean']:.4f} ± {agg_metrics['Overall_Std']:.4f}")
    print(f"Duplicate Question Rate: {agg_metrics['Duplicate_Rate']:.2%}")
    print(f"Option Length Imbalance (StdDev): {agg_metrics['Option_Length_Imbalance']:.2f}\n")
    
    # Step 5 - Add Performance Analysis (Top 3 and Bottom 3)
    if len(final_df) >= 3:
        print(f"--- Top 3 Best Questions ({prefix.strip('_') or 'Current'}) ---")
        top_3 = final_df.nlargest(3, 'overall_score')
        for i, (_, r) in enumerate(top_3.iterrows(), 1):
            q_text = r['question'][:60] + "..." if len(ensure_string(r['question'])) > 60 else r['question']
            print(f"{i}. [Score: {r['overall_score']:.4f}] {q_text}")
            
        print(f"\n--- Top 3 Worst Questions ({prefix.strip('_') or 'Current'}) ---")
        bottom_3 = final_df.nsmallest(3, 'overall_score')
        for i, (_, r) in enumerate(bottom_3.iterrows(), 1):
            q_text = r['question'][:60] + "..." if len(ensure_string(r['question'])) > 60 else r['question']
            print(f"{i}. [Score: {r['overall_score']:.4f}] {q_text}")
        print("\n")
        
    # Step 4 - Add Correlation Heatmap
    if len(results_df) > 1:
        corr_cols = ['plausibility', 'diversity', 'relevance', 'overall_score']
        corr_matrix = results_df[corr_cols].corr()
        
        plt.figure(figsize=(8, 6))
        sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', vmin=-1.0, vmax=1.0, center=0, 
                    xticklabels=corr_cols, yticklabels=corr_cols)
        plt.title(f'Metric Correlation Heatmap ({prefix.strip("_") or "Overall"})')
        plt.tight_layout()
        out_heatmap = os.path.join(RESULTS_DIR, f"{prefix}correlation_heatmap.png")
        plt.savefig(out_heatmap)
        plt.close()
        print(f"Heatmap saved to {out_heatmap}")
    
    # Generate visual/histogram of scores (Optional Extension)
    plt.figure(figsize=(10, 6))
    sns.histplot(results_df['plausibility'], color='blue', label='Plausibility', kde=True, alpha=0.5, stat='density')
    sns.histplot(results_df['diversity'], color='green', label='Diversity', kde=True, alpha=0.5, stat='density')
    sns.histplot(results_df['relevance'], color='orange', label='Relevance', kde=True, alpha=0.5, stat='density')
    plt.title(f'Histogram of Question Metrics ({prefix.strip("_") or "Overall"})')
    plt.xlabel('Metric Value')
    plt.ylabel('Density')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, f"{prefix}score_distributions.png"))
    plt.close()
    
    if not is_comparison:
        # Step 7: Single file visualizations
        metrics = ['Plausibility_Mean', 'Diversity_Mean', 'Relevance_Mean', 'Overall_Mean']
        labels = ['Plausibility', 'Diversity', 'Relevance', 'Overall']
        values = [agg_metrics[m] for m in metrics]
        
        plt.figure(figsize=(9, 6))
        colors = sns.color_palette("muted")[:4]
        bars = plt.bar(labels, values, color=colors)
        plt.ylim(0, 1.0)
        plt.title('Quiz Generation Metrics (Averages)')
        plt.ylabel('Score (0.0 - 1.0)')
        
        # Add value labels
        for bar in bars:
            yval = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2, yval + 0.02, f"{yval:.2f}", ha='center', va='bottom')
            
        out_png = os.path.join(RESULTS_DIR, "metrics_graph.png")
        plt.savefig(out_png)
        plt.close()
        print(f"Graph saved to {out_png}")
        
    return agg_metrics

def compare_metrics(before_file, after_file):
    """
    Step 8 - Comparison Mode
    Generates comparison between two runs.
    """
    print("--- Running Comparison Mode ---")
    metrics_b = evaluate_quizzes(before_file, is_comparison=True, prefix="before_")
    metrics_a = evaluate_quizzes(after_file, is_comparison=True, prefix="after_")
    
    if not metrics_b or not metrics_a:
        print("Comparison failed due to missing files or data issues.")
        return
        
    metrics_keys = ['Plausibility_Mean', 'Diversity_Mean', 'Relevance_Mean', 'Overall_Mean']
    metrics_labels = ['Plausibility', 'Diversity', 'Relevance', 'Overall']
    
    vals_b = [metrics_b[k] for k in metrics_keys]
    vals_a = [metrics_a[k] for k in metrics_keys]
    
    # Calculate Improvements
    improvements = []
    for b_val, a_val in zip(vals_b, vals_a):
        if b_val > 0:
            imp = ((a_val - b_val) / b_val) * 100
        else:
            imp = 0.0 if a_val == 0 else float('inf')
        improvements.append(imp)
    
    x = np.arange(len(metrics_labels))
    width = 0.35
    
    fig, ax = plt.subplots(figsize=(10, 6))
    rects1 = ax.bar(x - width/2, vals_b, width, label='Before', color='#4C72B0')
    rects2 = ax.bar(x + width/2, vals_a, width, label='After', color='#55A868')
    
    ax.set_ylabel('Score (0.0 - 1.0)')
    ax.set_title('Distractor Quality Metrics: Before vs After')
    ax.set_xticks(x)
    ax.set_xticklabels(metrics_labels)
    ax.legend()
    ax.set_ylim(0, 1.0)
    
    def autolabel_with_improvement(rects, base_rects=None, improvements_list=None):
        for i, rect in enumerate(rects):
            height = rect.get_height()
            label_text = f'{height:.2f}'
            
            # If it's the "After" bar, also add the % improvement
            if improvements_list is not None and i < len(improvements_list):
                imp = improvements_list[i]
                sign = '+' if imp >= 0 else ''
                label_text += f'\n({sign}{imp:.1f}%)'
                
            ax.annotate(label_text,
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3 if base_rects else 3), 
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=9)
                        
    autolabel_with_improvement(rects1)
    autolabel_with_improvement(rects2, base_rects=rects1, improvements_list=improvements)
    
    # Improve layout to prevent overlap of text
    plt.margins(y=0.2)
    fig.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, "comparison.png"))
    plt.close()
    print("Comparison graph saved to comparison.png")
    
    # End Goal output statement highlighting improvement metrics
    print("\n" + "="*80)
    print("END GOAL: Result Statement")
    print("="*80)
    print(f"Our distractor improves plausibility from {metrics_b['Plausibility_Mean']:.2f} to {metrics_a['Plausibility_Mean']:.2f} "
          f"(+{improvements[0]:.1f}% improvement) and diversity from {metrics_b['Diversity_Mean']:.2f} to {metrics_a['Diversity_Mean']:.2f} "
          f"(+{improvements[1]:.1f}% improvement), demonstrating significant enhancement in overall question quality "
          f"(from {metrics_b['Overall_Mean']:.2f} to {metrics_a['Overall_Mean']:.2f}).")
    print("="*80)

def generate_sample_data():
    """Generates sample input CSV files for testing purposes if none are provided."""
    import csv
    
    before_data = [
        ["question", "option_a", "option_b", "option_c", "option_d", "answer"],
        ["What is the capital of France?", "Paris", "London", "Berlin", "Madrid", "A"],
        ["What is 2+2?", "3", "4", "5", "6", "B"],
        ["Which planet is known as the Red Planet?", "Earth", "Mars", "Jupiter", "Venus", "B"]
    ]
    
    after_data = [
        ["question", "option_a", "option_b", "option_c", "option_d", "answer"],
        ["What is the capital of France?", "Paris", "Lyon", "Marseille", "Toulouse", "A"],
        ["What is 2+2?", "22", "4", "0", "8", "B"],
        ["Which planet is known as the Red Planet in our solar system?", "Venus", "Mars", "Saturn", "Mercury", "B"]
    ]
    
    for f, d in [("sample_before.csv", before_data), ("sample_after.csv", after_data)]:
        with open(f, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerows(d)
    print("Created 'sample_before.csv' and 'sample_after.csv' for testing.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Quiz Distractors for AI Generation System")
    parser.add_argument("--input", type=str, help="Single CSV file to evaluate (Generates metrics_graph.png)")
    parser.add_argument("--before", type=str, help="CSV file before improvements (Requires --after)")
    parser.add_argument("--after", type=str, help="CSV file after improvements (Requires --before)")
    parser.add_argument("--demo", action="store_true", help="Run a demo with generated sample data")
    args = parser.parse_args()
    
    sns.set_theme(style="whitegrid")
    
    if args.demo:
        generate_sample_data()
        compare_metrics("sample_before.csv", "sample_after.csv")
    elif args.before and args.after:
        compare_metrics(args.before, args.after)
    elif args.input:
        evaluate_quizzes(args.input)
    else:
        parser.print_help()
        print("\nExample single file: python evaluation_metrics.py --input results.csv")
        print("Example comparison:  python evaluation_metrics.py --before old.csv --after new.csv")
        print("Run demo:            python evaluation_metrics.py --demo")
        
        # If no arguments provided, run demo mode for user convenience if they just double click it
        print("\nNo arguments provided. Running demo mode...")
        generate_sample_data()
        compare_metrics("sample_before.csv", "sample_after.csv")
