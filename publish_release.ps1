param (
    [string]$Type = "patch"
)

$ValidTypes = @("major", "minor", "patch")
if ($ValidTypes -notcontains $Type) {
    Write-Host "Type de mise à jour invalide. Utilisez 'major', 'minor' ou 'patch'." -ForegroundColor Red
    exit 1
}

Write-Host "Mise a jour de la version ($Type)..." -ForegroundColor Cyan

# Bump frontend package.json version
Push-Location frontend
npm version $Type --no-git-tag-version | Out-Null
$NewVersion = (Get-Content package.json | ConvertFrom-Json).version
Pop-Location

# Remove 'v' prefix if it exists in npm output, though standard is without in our VERSION file
$CleanVersion = $NewVersion -replace '^v', ''

# Update root VERSION file
$CleanVersion | Out-File -Encoding utf8 -FilePath VERSION

# Update backend VERSION file
$CleanVersion | Out-File -Encoding utf8 -FilePath backend/VERSION

Write-Host "Nouvelle version : v$CleanVersion" -ForegroundColor Green

Write-Host "Construction de l'image Docker (Architecture courante, generalement x86_64)..." -ForegroundColor Cyan
docker build -f Dockerfile.standalone -t aschefr/alanbix:$CleanVersion -t aschefr/alanbix:latest .

# Note pour plus tard : Pour compiler pour ARM et x86 en meme temps, de-commente cette ligne :
# docker buildx build --platform linux/amd64,linux/arm64 -f Dockerfile.standalone -t aschefr/alanbix:$CleanVersion -t aschefr/alanbix:latest --push .

Write-Host "Poussee de l'image vers Docker Hub..." -ForegroundColor Cyan
docker push aschefr/alanbix:$CleanVersion
docker push aschefr/alanbix:latest

Write-Host "Termine ! Alanbix v$CleanVersion a ete publie avec succes." -ForegroundColor Green
