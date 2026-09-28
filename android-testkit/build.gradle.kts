import org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
import org.jetbrains.kotlin.gradle.dsl.abi.ExperimentalAbiValidation

plugins {
    kotlin("jvm") version "2.4.20"
    id("com.vanniktech.maven.publish") version "0.37.0"
}

group = "io.github.pedronveloso"
version = providers.gradleProperty("VERSION_NAME").get()

repositories {
    mavenCentral()
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    explicitApi()
    @OptIn(ExperimentalAbiValidation::class)
    abiValidation()
    compilerOptions {
        jvmTarget = JVM_17
    }
}

tasks.withType<Jar>().configureEach {
    from(rootProject.file("../LICENSE")) {
        into("META-INF")
    }
}

dependencies {
    testImplementation(kotlin("test"))
}

mavenPublishing {
    coordinates(
        groupId = "io.github.pedronveloso",
        artifactId = "aasg-testkit",
        version = project.version.toString(),
    )
    publishToMavenCentral()
    signAllPublications()

    pom {
        name = "AASG Android Testkit"
        description = "Gesture timelines and readable pacing for AASG Android recording journeys"
        inceptionYear = "2026"
        url = "https://github.com/pedronveloso/AASG"
        licenses {
            license {
                name = "The Apache License, Version 2.0"
                url = "https://www.apache.org/licenses/LICENSE-2.0.txt"
                distribution = "https://www.apache.org/licenses/LICENSE-2.0.txt"
            }
        }
        developers {
            developer {
                id = "pedronveloso"
                name = "Pedro Veloso"
                email = "pedro.n.veloso@gmail.com"
                url = "https://github.com/pedronveloso"
            }
        }
        scm {
            url = "https://github.com/pedronveloso/AASG"
            connection = "scm:git:git://github.com/pedronveloso/AASG.git"
            developerConnection = "scm:git:ssh://git@github.com/pedronveloso/AASG.git"
        }
    }
}
