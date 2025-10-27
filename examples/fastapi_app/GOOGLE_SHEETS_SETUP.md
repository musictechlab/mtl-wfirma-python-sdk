# Google Sheets Integration Setup

This application now includes integration with Google Sheets to fetch financial data including year, month, day, contractor, payment date, and gross amount.

## Setup Instructions

### 1. Install Dependencies

Make sure you have installed the required Google API dependencies:

```bash
pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2
```

### 2. Google Cloud Console Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Sheets API:
   - Go to "APIs & Services" > "Library"
   - Search for "Google Sheets API"
   - Click on it and enable it

### 3. Create Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth client ID"
3. Choose "Desktop application" as the application type
4. Download the JSON file and rename it to `credentials.json`
5. Place the `credentials.json` file in the `examples/fastapi_app/` directory

### 4. Configure Spreadsheet Access

1. Open your Google Sheets document: https://docs.google.com/spreadsheets/d/1zAnT2vmr8W4eusylPdJsKEXKcLhQ_NVBv86WQ8R_kpU/edit?gid=1701641961#gid=1701641961
2. Make sure the spreadsheet is accessible (either public or shared with the Google account you'll authenticate with)
3. The application expects the following columns in the first row (headers):
   - Year
   - Month  
   - Day
   - Contractor
   - Data płatności (Payment Date)
   - Kwota brutto (Gross Amount)

### 5. First Run Authentication

When you first run the application and try to access the Google Sheets data:

1. The application will open a browser window for Google OAuth authentication
2. Sign in with your Google account
3. Grant permissions to access your Google Sheets
4. The application will save the authentication token in `token.json` for future use

### 6. Access the Data

Once set up, you can access the Google Sheets data through:

- **Web Interface**: Navigate to `/google-sheets` in your browser
- **API Endpoints**:
  - `/api/google-sheets/raw` - Raw data from Google Sheets
  - `/api/google-sheets/parsed` - Parsed and formatted data with statistics

## Data Structure

The parsed data includes:

- **Year**: Extracted from payment date
- **Month**: Extracted from payment date  
- **Day**: Extracted from payment date
- **Contractor**: Contractor name
- **Payment Date**: Original payment date string
- **Gross Amount**: Parsed as float value

## Summary Statistics

The application automatically calculates:

- Total number of records
- Total gross amount
- Number of unique contractors
- Average amount per record
- Breakdown by year
- Breakdown by month
- Breakdown by contractor

## Troubleshooting

### Common Issues

1. **"Google Sheets credentials file not found"**
   - Make sure `credentials.json` is in the correct directory
   - Verify the file name is exactly `credentials.json`

2. **"Permission denied"**
   - Check that the Google Sheets document is accessible
   - Verify the Google account has access to the spreadsheet

3. **"No data available"**
   - Check that the spreadsheet has data in the expected format
   - Verify the range configuration in the code matches your data

### File Structure

```
examples/fastapi_app/
├── credentials.json          # Google OAuth credentials (you need to add this)
├── token.json               # Authentication token (auto-generated)
├── main.py                  # Main application with Google Sheets integration
├── templates/
│   └── google_sheets.html   # Web template for displaying data
└── requirements.txt         # Updated with Google API dependencies
```

## Security Notes

- Keep your `credentials.json` file secure and never commit it to version control
- The `token.json` file contains sensitive authentication data and should also be kept secure
- Consider using environment variables for production deployments
