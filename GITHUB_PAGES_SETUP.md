# GitHub Pages Setup Instructions

## ✅ Steps to Enable GitHub Pages

### 1. Access Repository Settings
1. Navigate to your repository: `https://github.com/blmothapo1/blmothapo1`
2. Click on **Settings** tab
3. Scroll down to **Pages** section in the left sidebar

### 2. Configure GitHub Pages Source
1. Under **Source**, select:
   - **Branch**: `main` (or merge this PR branch to main first)
   - **Folder**: `/ (root)`
2. Click **Save**

### 3. Custom Domain Configuration
The CNAME file is already configured with `sterlingenergyinfrastructure.com`

#### DNS Configuration Required:
You need to configure your domain's DNS settings with your domain registrar:

**A Records** (for apex domain):
```
Type: A
Name: @
Value: 185.199.108.153

Type: A
Name: @
Value: 185.199.109.153

Type: A
Name: @
Value: 185.199.110.153

Type: A
Name: @
Value: 185.199.111.153
```

**CNAME Record** (for www subdomain):
```
Type: CNAME
Name: www
Value: blmothapo1.github.io.
```

### 4. Enable HTTPS
1. After DNS propagates (24-48 hours), return to GitHub Pages settings
2. Check the box for **Enforce HTTPS**
3. GitHub will automatically provision an SSL certificate

### 5. Verify Deployment
Once configured, your site will be available at:
- `https://sterlingenergyinfrastructure.com`
- `https://blmothapo1.github.io/blmothapo1` (GitHub Pages URL)

## 📋 Checklist

- [ ] Merge this PR to main branch
- [ ] Enable GitHub Pages in repository settings
- [ ] Configure DNS records at domain registrar
- [ ] Wait for DNS propagation (24-48 hours)
- [ ] Verify custom domain resolution
- [ ] Enable HTTPS in GitHub Pages settings
- [ ] Test live site at https://sterlingenergyinfrastructure.com

## 🔍 Verification Steps

### Check DNS Propagation:
```bash
# Check A records
dig sterlingenergyinfrastructure.com A +short

# Check CNAME for www
dig www.sterlingenergyinfrastructure.com CNAME +short
```

### Test Site Accessibility:
```bash
# Test HTTP response
curl -I https://sterlingenergyinfrastructure.com
```

## 📁 Files Deployed

- `index.html` - Main landing page
- `CNAME` - Custom domain configuration
- `.nojekyll` - Disables Jekyll processing
- `robots.txt` - Search engine directives
- `sitemap.xml` - SEO sitemap
- `.gitignore` - Git ignore rules
- `DEPLOYMENT.md` - Deployment documentation

## 🎨 Design Features

- Modern, responsive Tailwind CSS design
- Investor-ready professional layout
- Mobile-first responsive approach
- Fast loading with CDN resources
- SEO-optimized with meta tags
- Clean navigation and sections

## 📊 SEO Optimization

- ✅ Semantic HTML5 structure
- ✅ Meta descriptions and keywords
- ✅ XML sitemap for search engines
- ✅ Robots.txt for crawler directives
- ✅ Responsive viewport meta tag
- ✅ Social media ready structure

## 🚀 Performance

- Lightweight HTML/CSS
- CDN-hosted Tailwind CSS
- Inline critical CSS for animations
- No build process required
- Fast Time to First Byte (TTFB)

## 🛠️ Troubleshooting

### Issue: Custom domain not working
- **Solution**: Verify DNS records are correctly configured and propagated

### Issue: HTTPS not available
- **Solution**: Wait 24-48 hours after DNS propagation, then enable in settings

### Issue: 404 errors
- **Solution**: Ensure GitHub Pages is enabled and pointing to main branch root

### Issue: Styles not loading
- **Solution**: Tailwind CSS is loaded from CDN - check internet connectivity

## 📞 Support

For issues with:
- **GitHub Pages**: GitHub Support or Documentation
- **DNS Configuration**: Your domain registrar's support
- **Site Content**: Update files in repository and push changes

---

**Last Updated**: 2025-11-01
