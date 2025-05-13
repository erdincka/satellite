# Satellite image processing using Data Fabric & AI

## Installation

### Clone the repository
git clone https://github.com/erdincka/satellite.git

### Navigate to the project directory
cd satellite

### Create venv
python3 -m venv .venv

### Activate virtual environment
source .venv/bin/activate

### Install dependencies
pip install -r requirements.txt

### Extract images if using offline files
mkdir -p images; tar -xf ./downloaded_images.tar images/

### Run the application
streamlit run main.py

## TODO

A lot
