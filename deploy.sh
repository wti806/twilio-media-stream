
#!/bin/bash
gcloud run deploy twilio-media-ws --source . --project df-integration-demo --region us-central1 --allow-unauthenticated --min-instances 1 --service-account integration-connector-sa@df-integration-demo.iam.gserviceaccount.com