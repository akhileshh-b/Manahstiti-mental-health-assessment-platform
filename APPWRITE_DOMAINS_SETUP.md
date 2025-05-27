# Appwrite Domain Configuration Fix

## Issue
You're getting this error:
```json
{
  "message": "Invalid `success` param: URL host must be one of: localhost, appwrite.io, *.appwrite.io, fra.cloud.appwrite.io",
  "code": 400,
  "type": "general_argument_invalid",
  "version": "1.6.2"
}
```

## Solution

### 1. Configure Allowed Domains in Appwrite Console

1. Go to your Appwrite Console: https://fra.cloud.appwrite.io/console
2. Select your project: `manahstiti-mental-health-lays`
3. Go to **Settings** → **Domains**
4. Add the following domains to your **Allowed Origins**:
   - `http://localhost:5000`
   - `http://127.0.0.1:5000`
   - `http://localhost:3000` (if you use different ports)
   - Your production domain when you deploy

### 2. Configure OAuth Redirect URLs

1. In Appwrite Console, go to **Auth** → **Settings**
2. Under **OAuth2 Providers**, configure Google OAuth:
   - **Success URL**: `http://localhost:5000/assessment`
   - **Failure URL**: `http://localhost:5000/login`

### 3. Code Changes Made

The following files have been updated to use proper URL handling:

- `templates/login.html`: Fixed OAuth2 redirect URLs
- `templates/verify-email.html`: Fixed email verification URLs

### 4. Test the Fix

1. Restart your Flask application
2. Try the Google OAuth login
3. Try email verification

The error should now be resolved!

## For Production Deployment

When you deploy to production, update the `getBaseUrl()` function in both files to include your production domain:

```javascript
function getBaseUrl() {
  const hostname = window.location.hostname;
  const port = window.location.port;
  
  // For localhost development
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return `http://localhost:${port || '5000'}`;
  }
  
  // For production - replace with your actual domain
  if (hostname === 'your-domain.com') {
    return 'https://your-domain.com';
  }
  
  // Default fallback
  return 'http://localhost:5000';
}
```

And add your production domain to Appwrite's allowed origins. 