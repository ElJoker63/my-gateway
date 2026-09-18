// Package crypto provides AES-256-GCM helpers for encrypting secrets at rest
// (per-user provider keys, OAuth tokens).
//
// The master key comes from GATEWAY_MASTER_KEY (32+ bytes string, hashed to 32-byte
// key). If unset and GATEWAY_API_KEY is set, that is used as fallback — with a
// loud warning since API keys often repeat short strings.
package crypto

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"

	stdrand "crypto/rand"
)

// Errors exportable to callers.
var (
	ErrShortCiphertext = errors.New("ciphertext too short")
	ErrNoMasterKey     = errors.New("GATEWAY_MASTER_KEY not set")
)

// masterKey returns the AES key. If neither env var is set, refuses.
func masterKey() ([]byte, error) {
	if mk := os.Getenv("GATEWAY_MASTER_KEY"); mk != "" {
		h := sha256.Sum256([]byte(mk))
		return h[:], nil
	}
	if mk := os.Getenv("GATEWAY_API_KEY"); mk != "" {
		h := sha256.Sum256([]byte(mk))
		return h[:], nil
	}
	return nil, ErrNoMasterKey
}

// Encrypt encrypts plain with AES-GCM and prepends the nonce.
func Encrypt(plain []byte) ([]byte, error) {
	key, err := masterKey()
	if err != nil {
		return nil, err
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	nonce := make([]byte, aead.NonceSize())
	if _, err := stdrand.Read(nonce); err != nil {
		return nil, err
	}
	return aead.Seal(nonce, nonce, plain, nil), nil
}

// Decrypt reverses Encrypt.
func Decrypt(blob []byte) ([]byte, error) {
	key, err := masterKey()
	if err != nil {
		return nil, err
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	ns := aead.NonceSize()
	if len(blob) < ns {
		return nil, ErrShortCiphertext
	}
	return aead.Open(nil, blob[:ns], blob[ns:], nil)
}

// Hash is sha256(text) as hex — for storing API keys under lookup.
func Hash(s string) string { return hex.EncodeToString(sha256Sum([]byte(s))) }

// KeyDisplay masks an API key for UIs: shows the prefix and last 2 chars.
func KeyDisplay(raw string) string {
	if len(raw) <= 6 {
		return "****"
	}
	return raw[:8] + "…" + raw[len(raw)-2:]
}

func sha256Sum(b []byte) []byte {
	h := sha256.Sum256(b)
	return h[:]
}
