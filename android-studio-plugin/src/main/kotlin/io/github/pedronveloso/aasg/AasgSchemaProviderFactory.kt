package io.github.pedronveloso.aasg

import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.jetbrains.jsonSchema.extension.JsonSchemaFileProvider
import com.jetbrains.jsonSchema.extension.JsonSchemaProviderFactory
import com.jetbrains.jsonSchema.extension.SchemaType

class AasgSchemaProviderFactory : JsonSchemaProviderFactory, DumbAware {
    override fun getProviders(project: Project): List<JsonSchemaFileProvider> =
        listOf(
            object : JsonSchemaFileProvider {
                override fun isAvailable(file: VirtualFile): Boolean =
                    AasgYaml.isConfigName(file.name)

                override fun getName(): String = "AASG configuration (schema 9)"

                override fun getSchemaFile(): VirtualFile? =
                    JsonSchemaProviderFactory.getResourceFile(
                        AasgSchemaProviderFactory::class.java,
                        "/schemas/aasg.schema.json",
                    )

                override fun getSchemaType(): SchemaType = SchemaType.embeddedSchema
            }
        )
}
