# Visual Diff Tool

A Flask and Playwright tool for visual regression testing of websites. It allows for single URL comparisons and batch processing via CSV upload.

## Features

-   **Single Comparison:** Compare two URLs directly.
-   **Batch Comparison:** Upload a CSV of URL pairs for automated testing.
-   **Multiple Viewports:** Test on Desktop, Tablet, and Mobile resolutions.
-   **Pixel-Level Diffing:** Generates a "diff" image highlighting differences.
-   **Filterable Results:** The batch results page allows for easy filtering.

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/visual-diff-tool.git
    cd visual-diff-tool
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: .\venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Install Playwright's browser binaries:**
    ```bash
    playwright install
    ```

## How to Run

1.  Start the Flask server:
    ```bash
    flask run
    ```
2.  Open your web browser and navigate to `http://127.0.0.1:5000`.

## How to Use

-   **Single Mode:** Enter the two URLs you want to compare and click "Generate Comparison".
-   **Batch Mode:** Create a CSV file with two columns: `old_url` and `new_url`. Upload the file to start the background job.