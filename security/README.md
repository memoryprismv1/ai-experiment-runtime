# Cognitive experiment artifact encryption

GitHub Actions artifacts in this public repository are downloadable by repository readers. The cognitive-skill workflow therefore encrypts **all scorer packets** and **all controller/raw experiment evidence** before upload.

The workflow uses the recipient public key in `security/cognitive-experiment-artifact-public.asc`.

- Recipient fingerprint: `92EF77B3A3015677D0BF226D2669E787A734C1ED`
- Scorer bundle: contains only blind IDs, task prompts, responses and the rubric. It does not contain the condition key.
- Controller bundle: contains the condition key, run specifications, raw Q-Batch evidence, reports and index.
- The two bundles are encrypted separately so the scorer bundle can be decrypted and reviewed without opening the controller key.
- The corresponding private key is held outside this repository by the experiment custodian. **Never commit or upload the private key or its passphrase.**

## Decrypt

Import the separately supplied private key:

```bash
gpg --import cognitive-experiment-artifact-private.asc
```

Decrypt the scorer bundle first:

```bash
gpg --output scorer-packets.tar.gz --decrypt scorer-packets.tar.gz.gpg
tar -tzf scorer-packets.tar.gz
```

Do not decrypt the controller bundle until all blind scores have been completed and locked.

Then decrypt the controller bundle:

```bash
gpg --output controller-and-evidence.tar.gz --decrypt controller-and-evidence.tar.gz.gpg
tar -tzf controller-and-evidence.tar.gz
```

GPG prompts for the private-key passphrase during decryption. Keep the passphrase separate from the private-key file.
