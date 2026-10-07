/**
 * Copy frontend dependencies from node_modules to static/
 * 
 * Dependencies:
 * - htmx.org → static/js/htmx.min.js
 * - alpinejs → static/js/alpine.min.js
 * - flowbite → static/js/flowbite.min.js
 * 
 * Usage: npm run build:js
 */

const fs = require('fs');
const path = require('path');

// Configuración de dependencias
const dependencies = [
    {
        name: 'HTMX',
        from: path.join('node_modules', 'htmx.org', 'dist', 'htmx.min.js'),
        to: path.join('src', 'static', 'js', 'htmx.min.js')
    },
    {
        name: 'Alpine.js',
        from: path.join('node_modules', 'alpinejs', 'dist', 'cdn.min.js'),
        to: path.join('src', 'static', 'js', 'alpine.min.js')
    },
    {
        name: 'Flowbite',
        from: path.join('node_modules', 'flowbite', 'dist', 'flowbite.min.js'),
        to: path.join('src', 'static', 'js', 'flowbite.min.js')
    }
];

// Función principal
function copyDependencies() {
    console.log('\nCopying frontend dependencies to static/...\n');

    // Asegurar que existe la carpeta destino
    const destDir = path.join('src', 'static', 'js');
    if (!fs.existsSync(destDir)) {
        fs.mkdirSync(destDir, { recursive: true });
        console.log(`Created directory: ${destDir}\n`);
    }

    // Copiar cada dependencia
    let successCount = 0;
    let errorCount = 0;

    dependencies.forEach(({ name, from, to }) => {
        try {
            // Verificar que existe el archivo fuente
            if (!fs.existsSync(from)) {
                console.error(`${name}: Source file not found`);
                console.error(`   Expected: ${from}`);
                console.error(`   Run 'npm install' first!\n`);
                errorCount++;
                return;
            }

            // Copiar archivo
            fs.copyFileSync(from, to);

            // Obtener tamaño
            const stats = fs.statSync(to);
            const sizeKB = (stats.size / 1024).toFixed(2);

            // Log success
            console.log(`${name.padEnd(12)} → ${path.relative(process.cwd(), to)} (${sizeKB} KB)`);
            successCount++;

        } catch (error) {
            console.error(`${name}: ${error.message}\n`);
            errorCount++;
        }
    });

    // Resumen
    console.log(`\nSummary: ${successCount} copied, ${errorCount} failed`);

    if (errorCount > 0) {
        console.log('\nSome dependencies failed to copy. Check errors above.\n');
        process.exit(1);
    }

    console.log('All frontend dependencies copied successfully!\n');
}

// Ejecutar
copyDependencies();
