# Sterling Energy Infrastructure

Official landing page for Sterling Energy Infrastructure - Powering Tomorrow's Energy Solutions.

## 🌐 Live Site

Visit us at: [https://sterlingenergyinfrastructure.com](https://sterlingenergyinfrastructure.com)

## 🚀 Deployment

This site is deployed using GitHub Pages. The landing page is hosted directly from the `main` branch root directory.

### GitHub Pages Configuration

To enable GitHub Pages for this repository:

1. Go to Repository Settings
2. Navigate to "Pages" section
3. Under "Source", select:
   - **Branch**: `main`
   - **Folder**: `/ (root)`
4. Click "Save"
5. Custom domain is configured via the `CNAME` file

### Custom Domain Setup

The custom domain `sterlingenergyinfrastructure.com` is configured through:
- The `CNAME` file in the repository root
- DNS settings pointing to GitHub Pages

**Required DNS Records:**
```
Type: A
Host: @
Value: 185.199.108.153
       185.199.109.153
       185.199.110.153
       185.199.111.153

Type: CNAME
Host: www
Value: blmothapo1.github.io
```

### HTTPS

GitHub Pages automatically provisions an SSL certificate for custom domains. After DNS propagation (usually 24-48 hours), HTTPS will be available.

## 📁 Repository Structure

```
/
├── index.html          # Main landing page
├── CNAME              # Custom domain configuration
├── .nojekyll          # Disables Jekyll processing
├── robots.txt         # SEO - Search engine directives
├── sitemap.xml        # SEO - Site structure for search engines
├── .gitignore         # Git ignore rules
└── README.md          # This file
```

## 🎨 Design

The landing page features:
- Modern, responsive design using Tailwind CSS
- Clean, professional layout optimized for investors
- Mobile-first responsive design
- Fast loading with CDN-based resources
- SEO-optimized structure

## 📊 SEO Features

- Semantic HTML structure
- Meta descriptions and keywords
- XML sitemap for search engines
- Robots.txt for crawler directives
- OpenGraph tags ready for social media

## 🔧 Technologies

- **HTML5** - Semantic markup
- **Tailwind CSS** - Utility-first CSS framework (CDN)
- **GitHub Pages** - Static site hosting
- **Custom Domain** - Professional branded URL

## 📝 License

© 2025 Sterling Energy Infrastructure. All rights reserved.
