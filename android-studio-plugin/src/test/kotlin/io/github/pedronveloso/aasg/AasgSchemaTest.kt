package io.github.pedronveloso.aasg

import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.fixtures.LightJavaCodeInsightFixtureTestCase
import com.jetbrains.jsonSchema.ide.JsonSchemaService
import org.jetbrains.yaml.psi.YAMLKeyValue
import org.jetbrains.yaml.schema.YamlJsonSchemaDocumentationProvider
import org.jetbrains.yaml.schema.YamlJsonSchemaHighlightingInspection

class AasgSchemaTest : LightJavaCodeInsightFixtureTestCase() {
    private val validConfig =
        """
        schema: 9
        android:
          test_task: connectedDebugAndroidTest
          additional_output_dir: app/build/outputs
          locale_argument: locale
          theme_argument: theme
        variants:
          locales: {en: en-US}
          themes: {light: light}
        captures:
          home:
            label: Home
            test: example.Capture
            artifacts: []
        """
            .trimIndent() + "\n"

    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(YamlJsonSchemaHighlightingInspection())
    }

    fun testBundledSchemaAttachesToBothNamesAndNestedFilesOnly() {
        val service = project.getService(JsonSchemaService::class.java)
        for (name in listOf("aasg.yaml", "aasg.yml")) {
            val file = myFixture.addFileToProject("nested/$name", validConfig)
            val schema = service.getSchemaObject(file)
            assertNotNull(schema)
            val provider = service.getSchemaProvider(schema!!)
            assertNotNull(provider)
            assertEquals("AASG configuration (schema 9)", provider!!.name)
            assertNotNull(provider.schemaFile)
        }
        val file = myFixture.configureByText("application.yaml", validConfig)
        assertNull(service.getSchemaObject(file))
    }

    fun testValidConfigAndStructuralErrors() {
        myFixture.configureByText("aasg.yaml", validConfig)
        assertEmpty(myFixture.doHighlighting().filter { it.description != null })
        for (invalid in
            listOf(
                validConfig.replace("schema: 9", "schema: 4"),
                validConfig.replace("schema: 9", "schema: true"),
                validConfig + "unexpected: true\n",
                validConfig.replace("    label: Home\n", ""),
                validConfig.replace("artifacts: []", "artifacts: wrong"),
                validConfig.replace("test_task:", "min_api: 0\n  test_task:"),
                validConfig.replace("artifacts: []", "navigation: impossible\n    artifacts: []"),
            )) {
            myFixture.configureByText("aasg.yaml", invalid)
            assertTrue(
                "Expected schema errors for:\n$invalid",
                myFixture.doHighlighting().any { it.description != null },
            )
        }
    }

    fun testKeyAndEnumCompletion() {
        myFixture.configureByText("aasg.yaml", "schema: 9\nproj<caret>\n")
        myFixture.completeBasic()
        assertTrue(myFixture.file.text.contains("project"))
        myFixture.configureByText("aasg.yaml", "captures:\n  home:\n    navigation: <caret>\n")
        val items = myFixture.completeBasic()!!.map { it.lookupString }
        assertTrue(items.containsAll(listOf("ignore", "gestural", "three-button", "all")))
    }

    fun testQuickDocumentationUsesFieldDescriptions() {
        val file = myFixture.configureByText("aasg.yaml", validConfig)
        val key =
            PsiTreeUtil.findChildrenOfType(file, YAMLKeyValue::class.java).first {
                it.keyText == "test"
            }
        val documentation = YamlJsonSchemaDocumentationProvider().generateDoc(key.key, key.key)
        assertNotNull(documentation)
        assertTrue(documentation!!.contains("Cmd/Ctrl-click"))
    }
}
