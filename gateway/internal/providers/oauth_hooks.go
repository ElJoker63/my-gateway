// OAuth hooks for providers.
//
// The API layer installs these once (from the oauth package) so providers can
// resolve tokens without an import cycle:
//   providers.SetOAuthHooks(tokenGetter, projectGetter)
package providers

import "errors"

var (
	// oauthToken returns the latest access token for a provider ("kiro",
	// "antigravity"), or "" when not connected.
	oauthToken = func(string) string { return "" }

	// oauthProject returns the Cloud Code project id (antigravity), or "".
	oauthProject = func(string) string { return "" }
)

// SetOAuthHooks registers the OAuth hook functions. Called once at boot by the
// api layer (which owns the oauth package import).
func SetOAuthHooks(token, project func(string) string) {
	if token != nil {
		oauthToken = token
	}
	if project != nil {
		oauthProject = project
	}
}

// cfgKeyFromOAuth reads a provider's OAuth access token (if connected).
func cfgKeyFromOAuth(provider string) string { return oauthToken(provider) }

// errOAuthNotConnected when the user has not finished the OAuth handshake.
var errOAuthNotConnected = errors.New("oauth not connected — finish the handshake via /api/oauth")

// antigravityProjectID returns the Cloud Code project id for antigravity.
func antigravityProjectID() (string, error) {
	if p := oauthProject("antigravity"); p != "" {
		return p, nil
	}
	return "", errOAuthNotConnected
}
