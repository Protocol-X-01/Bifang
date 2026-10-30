package com.bifang.companion

import android.content.Context
import android.content.SharedPreferences
import android.content.res.Configuration
import android.os.Bundle
import android.view.MenuItem
import android.view.View
import android.widget.Toast
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.view.WindowCompat
import androidx.drawerlayout.widget.DrawerLayout
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.floatingactionbutton.FloatingActionButton
import com.google.android.material.navigation.NavigationView

class MainActivity : AppCompatActivity() {
    
    private lateinit var drawerLayout: DrawerLayout
    private lateinit var navigationView: NavigationView
    private lateinit var bottomNavigation: BottomNavigationView
    private lateinit var fabInput: FloatingActionButton
    private lateinit var sharedPreferences: SharedPreferences
    
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        sharedPreferences = getSharedPreferences("bifang_prefs", Context.MODE_PRIVATE)
        
        applyTheme()
        
        setupViews()
        setupNavigation()
        setupGestures()
    }
    
    private fun applyTheme() {
        val themeMode = when (sharedPreferences.getString("theme", "system")) {
            "light" -> AppCompatDelegate.MODE_NIGHT_NO
            "dark" -> AppCompatDelegate.MODE_NIGHT_YES
            else -> AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM
        }
        AppCompatDelegate.setDefaultNightMode(themeMode)
    }
    
    private fun setupViews() {
        drawerLayout = findViewById(R.id.drawerLayout)
        navigationView = findViewById(R.id.navigationView)
        bottomNavigation = findViewById(R.id.bottomBar)
        fabInput = findViewById(R.id.fabInput)
        
        WindowCompat.setDecorFitsSystemWindows(window, false)
        
        val windowInsetsController = WindowCompat.getInsetsController(window, window.decorView)
        windowInsetsController.isAppearanceLightStatusBars = 
            (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) != Configuration.UI_MODE_NIGHT_YES
        windowInsetsController.isAppearanceLightNavigationBars = windowInsetsController.isAppearanceLightStatusBars
        
        fabInput.setOnClickListener {
            showQuickInputDialog()
        }
    }
    
    private fun setupNavigation() {
        bottomNavigation.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.nav_terminal -> {
                    showToast("Terminal view active")
                    true
                }
                R.id.nav_files -> {
                    showToast("Files browser coming soon")
                    true
                }
                R.id.nav_git -> {
                    showToast("Git integration coming soon")
                    true
                }
                R.id.nav_outputs -> {
                    showToast("Output manager coming soon")
                    true
                }
                else -> false
            }
        }
        
        bottomNavigation.setOnItemReselectedListener {
        }
        
        navigationView.setNavigationItemSelectedListener { menuItem ->
            handleDrawerItem(menuItem)
            drawerLayout.closeDrawer(navigationView)
            true
        }
        
        navigationView.setCheckedItem(R.id.nav_code_output)
    }
    
    private fun handleDrawerItem(item: MenuItem) {
        when (item.itemId) {
            R.id.nav_code_output -> {
                showToast("Code output panel active")
            }
            R.id.nav_environment -> {
                showToast("Environment manager coming soon")
            }
            R.id.nav_mcp_servers -> {
                showToast("MCP servers configuration...")
                showMCPServersDialog()
            }
            R.id.nav_context -> {
                showToast("Context manager coming soon")
            }
            R.id.nav_tools -> {
                showToast("Tools panel coming soon")
            }
            R.id.nav_settings -> {
                showToast("Opening settings...")
                openSettings()
            }
        }
    }
    
    private fun setupGestures() {
        drawerLayout.addDrawerListener(object : DrawerLayout.DrawerListener {
            override fun onDrawerSlide(drawerView: View, slideOffset: Float) {
            }
            
            override fun onDrawerOpened(drawerView: View) {
            }
            
            override fun onDrawerClosed(drawerView: View) {
            }
            
            override fun onDrawerStateChanged(newState: Int) {
            }
        })
    }
    
    private fun showQuickInputDialog() {
        showToast("Quick input coming soon")
    }
    
    private fun showMCPServersDialog() {
        val mcpInfo = """
            Librarian MCP: 9,236 tools
            Toolbox MCP: 14 tools
            Status: Connected ✓
        """.trimIndent()
        Toast.makeText(applicationContext, mcpInfo, Toast.LENGTH_LONG).show()
    }
    
    private fun openSettings() {
        val themeOptions = arrayOf("Light", "Dark", "System")
        val currentTheme = sharedPreferences.getString("theme", "system")
        val checkedItem = when (currentTheme) {
            "light" -> 0
            "dark" -> 1
            else -> 2
        }
        
        android.app.AlertDialog.Builder(this)
            .setTitle("Select Theme")
            .setSingleChoiceItems(themeOptions, checkedItem) { dialog, which ->
                val theme = when (which) {
                    0 -> "light"
                    1 -> "dark"
                    else -> "system"
                }
                sharedPreferences.edit().putString("theme", theme).apply()
                applyTheme()
                recreate()
                dialog.dismiss()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }
    
    private fun showToast(message: String) {
        Toast.makeText(applicationContext, message, Toast.LENGTH_SHORT).show()
    }
    
    override fun onBackPressed() {
        if (drawerLayout.isDrawerOpen(navigationView)) {
            drawerLayout.closeDrawer(navigationView)
        } else {
            super.onBackPressed()
        }
    }
}
